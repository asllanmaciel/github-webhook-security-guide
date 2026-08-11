# Idempotência de entregas com `X-GitHub-Delivery`

Validar a assinatura impede payloads adulterados, mas não impede que **uma entrega válida seja processada mais de uma vez**. O GitHub recomenda usar `X-GitHub-Delivery` para identificar cada entrega e informa que uma redelivery mantém o mesmo valor do header original.

> Importante: o GitHub não redelivera automaticamente entregas que falharam. Redeliveries podem ser disparadas manualmente ou por automação usando a API. Independentemente da origem, o consumidor deve ser seguro contra repetição.

Este guia usa um padrão de **inbox idempotente** com quatro etapas:

`claim → process → complete/fail`

A ideia é simples: antes de executar qualquer efeito de negócio, o consumidor tenta reservar atomicamente o identificador da entrega. Apenas um worker pode ganhar essa reserva.

## Ordem recomendada no endpoint

1. Leia o corpo bruto.
2. Valide `X-Hub-Signature-256`.
3. Valide limites básicos do request e o evento permitido.
4. Leia `X-GitHub-Delivery` como identificador opaco e limite seu tamanho antes de persistir.
5. Faça o `claim` atômico da delivery.
6. Responda `2xx` rapidamente e processe o trabalho na fila quando o fluxo for assíncrono.
7. Marque a delivery como `completed` ou `failed` conforme o resultado.

Nunca reserve um `X-GitHub-Delivery` antes de validar a assinatura. Caso contrário, um atacante pode preencher seu armazenamento com identificadores arbitrários e bloquear deliveries legítimas.

## Estados mínimos

Uma implementação simples pode manter estes campos:

| Campo | Uso |
|---|---|
| `delivery_id` | valor de `X-GitHub-Delivery`; chave única no escopo do provedor |
| `status` | `processing`, `completed` ou `failed` |
| `claim_token` | token aleatório ou versão usada para identificar o worker que possui a reserva |
| `lease_until` | limite para considerar um `processing` abandonado |
| `attempts` | número de tentativas aceitas pelo consumidor |
| `created_at` | primeira vez em que a delivery foi observada |
| `completed_at` | quando o processamento terminou com sucesso |
| `failed_at` | última falha conhecida |

Se o mesmo serviço recebe eventos de mais de um provedor, use uma chave composta como `provider + delivery_id`. Se quiser separar múltiplos webhooks GitHub dentro do mesmo serviço, acrescente também o identificador lógico do webhook à chave.

## Claim atômico

O ponto crítico é que `exists()` seguido de `insert()` **não é seguro**. Dois workers podem consultar ao mesmo tempo, ambos receberem "não existe" e executarem o mesmo efeito.

A reserva precisa ser uma única operação atômica: constraint `UNIQUE`, `INSERT ... ON CONFLICT`, `SET NX`, compare-and-set ou mecanismo equivalente.

Pseudocódigo independente de framework:

```text
function receiveWebhook(rawBody, headers):
    verifySignature(rawBody, headers["X-Hub-Signature-256"])

    deliveryId = requireBoundedOpaqueId(headers["X-GitHub-Delivery"])
    event       = requireAllowedEvent(headers["X-GitHub-Event"])

    claim = inbox.tryClaim(
        provider = "github",
        deliveryId = deliveryId,
        lease = 2 minutes
    )

    if claim.state == "completed":
        return 200

    if claim.state == "processing_by_other_worker":
        return 202

    if claim.state == "retry_not_allowed":
        return 202

    enqueue({
        deliveryId: deliveryId,
        event: event,
        claimToken: claim.token,
        rawBody: rawBody
    })

    return 202
```

No worker:

```text
function processJob(job):
    if !inbox.ownsClaim(job.deliveryId, job.claimToken):
        return

    try:
        performDomainOperationIdempotently(job.deliveryId, job.rawBody)
        inbox.complete(job.deliveryId, job.claimToken)
    catch transientError:
        inbox.fail(job.deliveryId, job.claimToken, retryable = true)
        throw transientError
    catch permanentError:
        inbox.fail(job.deliveryId, job.claimToken, retryable = false)
```

O `claim_token` funciona como um **fencing token**: um worker antigo não deve conseguir marcar a delivery como concluída depois que a lease expirou e outro worker a recuperou. Atualizações de `complete` e `fail` devem exigir que o token ainda seja o dono atual da reserva.

## Comportamento em concorrência

Ao receber a mesma delivery enquanto outra execução está ativa:

- `completed`: não execute o efeito novamente; responda `2xx`.
- `processing` com lease válida: trate como duplicata em andamento; não enfileire um segundo trabalho.
- `processing` com lease expirada: um único worker pode recuperar a delivery com compare-and-set e gerar um novo `claim_token`.
- `failed` retryable: permita nova tentativa apenas por transição atômica e respeite limite/backoff.
- `failed` permanente: mantenha o registro e não repita automaticamente o efeito.

Isso evita duas classes comuns de bug: concorrência simultânea e reprocessamento após redelivery.

## E se o processo morrer depois do claim?

O `lease_until` existe exatamente para esse caso. Se um worker reservar a delivery e morrer antes de concluí-la, a reserva não pode ficar presa para sempre.

Uma estratégia prática:

1. `processing` recebe uma lease curta, maior que o tempo esperado de processamento.
2. O worker pode renovar a lease enquanto ainda possui o mesmo `claim_token`.
3. Se a lease expirar, outra execução pode recuperar a delivery atomicamente.
4. O worker antigo perde o direito de fazer `complete/fail` quando o token muda.

**Atenção ao ponto mais difícil:** se o worker executar um efeito externo e morrer **depois do efeito, mas antes de marcar `completed`**, uma nova tentativa pode repetir esse efeito. O registro de delivery sozinho não cria garantia de "exactly once".

Para fechar essa janela:

- quando o efeito é no mesmo banco, grave a alteração de negócio e `completed` na mesma transação;
- quando o efeito é uma chamada externa, envie uma idempotency key derivada da delivery se a API de destino suportar;
- para fluxos mais complexos, use Inbox/Outbox e torne a operação de domínio idempotente pela própria chave de negócio.

O objetivo correto é **at-least-once delivery + efeitos idempotentes**, e não depender de uma promessa impossível de exactly-once entre sistemas independentes.

## TTL e retenção

Não use o mesmo TTL para todos os estados.

Sugestão inicial, a ser ajustada ao risco e ao volume:

| Estado | Retenção sugerida | Motivo |
|---|---:|---|
| `processing` | lease de 30 s a poucos minutos | liberar claims abandonados rapidamente |
| `failed` | dias ou semanas | permitir diagnóstico e retry controlado |
| `completed` | pelo menos 7 dias; frequentemente 30 dias ou mais | cobrir redeliveries, automações e replay dentro da janela de retenção |

A documentação do GitHub permite redelivery de entregas recentes e, atualmente, a interface/API trabalha com deliveries dos últimos 3 dias. Manter `completed` por pelo menos 7 dias dá uma margem operacional simples, mas isso **não é um limite de segurança**. Se sua ameaça inclui replay tardio ou se o custo de duplicação é alto, retenha a chave por mais tempo conforme sua política.

Não use apenas o TTL de `processing` como deduplicação: assim que ele expirar, uma delivery já concluída voltaria a ser aceita.

## SQL, Redis e filas: trade-offs

### Banco relacional

Bom padrão quando o efeito de negócio também está no banco. Use índice único e, quando possível, a mesma transação para inbox + alteração de domínio.

Exemplo conceitual:

```sql
CREATE TABLE webhook_deliveries (
    provider      VARCHAR(32)  NOT NULL,
    delivery_id   VARCHAR(128) NOT NULL,
    status        VARCHAR(16)  NOT NULL,
    claim_token   VARCHAR(64)  NULL,
    lease_until   TIMESTAMP    NULL,
    attempts      INTEGER      NOT NULL DEFAULT 0,
    created_at    TIMESTAMP    NOT NULL,
    completed_at  TIMESTAMP    NULL,
    failed_at     TIMESTAMP    NULL,
    PRIMARY KEY (provider, delivery_id)
);
```

A constraint é a proteção principal contra dois `claim`s simultâneos. A sintaxe exata do upsert depende do banco.

### Redis

`SET key token NX PX ...` é útil para claims rápidos, mas um lock temporário sozinho **não representa histórico de conclusão**. Mantenha um marcador de `completed` com TTL separado ou persista o resultado em armazenamento durável.

Se a perda do Redis puder causar efeitos duplicados inaceitáveis, ele não deve ser a única fonte de deduplicação.

### Fila

Uma fila ajuda a responder ao GitHub rapidamente, mas não substitui a idempotência. Mesmo filas com recursos de deduplicação normalmente têm janelas limitadas. Faça o claim no ponto em que você controla atomicidade e trate o worker como potencialmente executável mais de uma vez.

## Retry e backoff

Retry deve ser explícito:

- erros transitórios: timeout, indisponibilidade temporária, rate limit;
- erros permanentes: payload semanticamente inválido, recurso inexistente sem possibilidade de recuperação, evento não suportado.

Use backoff exponencial com jitter para falhas transitórias e limite de tentativas. Uma delivery permanentemente falha deve poder ser inspecionada ou enviada para uma dead-letter queue sem entrar em loop infinito.

## Observabilidade sem vazar dados

Registre metadados úteis:

- `delivery_id`;
- `X-GitHub-Event` e `action` quando aplicável;
- status (`processing`, `completed`, `failed`);
- número da tentativa;
- duração;
- classe/código do erro;
- timestamps de claim, conclusão e falha.

Evite registrar:

- webhook secret;
- header de assinatura completo;
- tokens de API;
- payload completo por padrão;
- campos sensíveis recebidos dentro do evento.

Se precisar guardar payload para troubleshooting ou replay interno, defina criptografia, controle de acesso e política de retenção separadamente.

## Checklist de implementação

- [ ] Assinatura validada antes do claim.
- [ ] `X-GitHub-Delivery` obrigatório e com tamanho limitado.
- [ ] Chave única por provedor/delivery.
- [ ] Claim realmente atômico.
- [ ] Duplicata `completed` retorna `2xx` sem novo efeito.
- [ ] Duplicata `processing` não cria um segundo job.
- [ ] Lease permite recuperar worker morto.
- [ ] `claim_token`/versão impede worker antigo de finalizar claim novo.
- [ ] Efeito de domínio também é idempotente.
- [ ] `completed` tem retenção maior que a lease.
- [ ] Retry tem backoff, limite e distinção entre erro transitório/permanente.
- [ ] Logs não contêm secret nem payload sensível por padrão.

## Referências oficiais

- [Best practices for using webhooks](https://docs.github.com/en/webhooks/using-webhooks/best-practices-for-using-webhooks)
- [Redelivering webhooks](https://docs.github.com/en/webhooks/testing-and-troubleshooting-webhooks/redelivering-webhooks)
- [Handling failed webhook deliveries](https://docs.github.com/en/webhooks/using-webhooks/handling-failed-webhook-deliveries)
