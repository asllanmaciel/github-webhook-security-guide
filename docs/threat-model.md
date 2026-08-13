# Threat model for GitHub webhook receivers

Validating `X-Hub-Signature-256` is necessary, but it is not a complete webhook security model.

This document separates the guarantees provided by the HMAC signature from the controls an application still needs around the receiver, queue and business logic.

## Assets worth protecting

A webhook receiver can reach much more than the HTTP endpoint itself. Typical assets include:

- the webhook secret;
- source-code and deployment credentials used by downstream automation;
- customer/project data reachable by event handlers;
- queue/storage infrastructure;
- audit logs and delivery history;
- business actions triggered by a valid event;
- availability of the endpoint and worker fleet.

Treat the receiver as an integration boundary, not as a trusted internal function just because GitHub is the sender.

## Trust boundaries

A practical flow looks like:

```text
Internet
  ↓ untrusted bytes
HTTPS endpoint
  ↓ signature + envelope validation
Accepted delivery store / queue
  ↓ authenticated internal job
Event handler
  ↓ business authorization
Side effects
```

Every arrow is a boundary where assumptions should be explicit.

The HTTP request is untrusted until the signature has been verified against the **exact raw body bytes** that were received.

A correctly signed event is authenticated as coming from a party that knows the shared secret, but its contents still need application-level validation before producing side effects.

## What HMAC verification gives you

When the secret remains confidential and verification is implemented correctly, `X-Hub-Signature-256` allows the receiver to detect payload modification and authenticate possession of the shared secret.

The receiver should:

1. read the raw request body without re-encoding it;
2. parse the `sha256=<hex>` signature format strictly;
3. compute HMAC-SHA-256 with the configured secret;
4. compare expected and received values in constant time;
5. reject the request before JSON/business processing when verification fails.

## What the signature does not give you

A valid signature does **not** by itself provide:

- confidentiality — use HTTPS;
- replay protection — track `X-GitHub-Delivery` and claim deliveries atomically;
- business authorization — an authenticated event may still be irrelevant or unsafe for a given repository/project;
- payload/schema correctness — validate the event and fields you consume;
- resource limits — enforce body size, timeouts and queue capacity;
- secret safety — protect secrets at rest and in logs;
- exactly-once effects — design handlers to be idempotent;
- downstream credential isolation — workers may hold more powerful credentials than the receiver needs.

## Threats and controls

| Threat | Example | Primary controls |
|---|---|---|
| Forged delivery | Attacker posts arbitrary JSON to the endpoint | HMAC verification, secret confidentiality |
| Payload tampering | Proxy/client changes bytes after signing | HMAC over exact raw body |
| Replay / redelivery | Same valid delivery reaches the handler more than once | `X-GitHub-Delivery`, atomic claim, idempotency |
| Event confusion | Receiver accepts an unexpected event type | `X-GitHub-Event` allowlist + payload validation |
| Cross-repository confusion | Valid event for repository A triggers project B | Validate repository/installation identity before side effects |
| Resource exhaustion | Very large payloads or request bursts consume workers | Request-size limit, rate limit, fast acknowledgement, queue limits |
| Secret leakage | Secret is printed in debug/error logs | Secret manager/env injection, structured redaction, least log retention |
| Sensitive payload leakage | Full webhook body contains private metadata and is retained forever | Data minimization, encryption, access control, retention policy |
| Duplicate side effect | Redelivery deploys/charges/notifies twice | Idempotent handlers and durable delivery state |
| Poison event | Valid but malformed/unexpected payload repeatedly crashes workers | Schema guards, dead-letter/quarantine path, bounded retries |
| Privilege escalation | Low-risk event reaches a worker with deployment/admin credentials | Separate handlers/credentials by capability, least privilege |

## Receiver responsibilities

The public-facing receiver should remain deliberately small.

A good receiver can:

- enforce HTTPS at the edge;
- reject requests above a documented body-size limit;
- verify the signature before decoding JSON;
- validate/allowlist the event type;
- capture `X-GitHub-Delivery`;
- persist or atomically claim the envelope;
- enqueue heavier processing;
- return a bounded response quickly.

Avoid performing long-running deployments, external API fan-out or destructive business operations directly inside the request lifecycle.

## Business authorization after signature verification

Authentication answers **who signed this payload**. Authorization answers **whether this event may cause this action here**.

Depending on the integration, verify context such as:

- repository owner/name or stable repository ID;
- installation/organization identity;
- expected branch/ref;
- event action (`opened`, `closed`, `published`, etc.);
- sender or team requirements when the workflow needs them;
- environment/project mapping;
- whether the requested operation is enabled for that repository.

Do not use repository names supplied by the payload to construct filesystem paths, shell commands or deployment targets without an explicit mapping/allowlist.

## Replay and concurrency

GitHub can redeliver legitimate events and infrastructure can deliver jobs more than once.

Use `X-GitHub-Delivery` as the stable delivery identifier and implement a durable state machine such as:

```text
received → claimed → processing → completed
                     ↘ failed/retry
```

The claim operation must be atomic. Two workers seeing the same delivery simultaneously should not both acquire the right to perform the side effect.

See [`idempotency.md`](idempotency.md) for SQL/Redis patterns, leases and retry guidance.

## Logging and forensic evidence

Useful audit metadata usually includes:

- delivery ID;
- event type/action;
- repository/installation identity;
- receive time;
- signature validation result without logging the secret/signature comparison material unnecessarily;
- processing state and attempt count;
- handler outcome/error category;
- correlation ID for downstream jobs.

Avoid logging secrets, authorization headers or entire payloads by default. If payload retention is required for troubleshooting/audit, define access control, encryption and deletion/retention rules explicitly.

## Secret compromise

If a webhook secret may have leaked:

1. treat signatures made with that secret as no longer trustworthy;
2. rotate the secret through the GitHub webhook configuration and receiver configuration;
3. audit logs/code/history for the leak source;
4. review accepted deliveries during the suspected exposure window;
5. rotate any downstream credentials that may also have been exposed;
6. document the incident and remediation.

Do not store webhook secrets in repository files, example payloads, screenshots or committed local environment files.

## Availability and failure behavior

Security failures should fail closed for the delivery, but a malformed/forged request should not exhaust the service.

Prefer:

- small request timeouts;
- bounded body reads;
- constant/cheap rejection paths;
- controlled retry counts;
- dead-letter/quarantine for poison events;
- metrics for invalid signatures, queue age and repeated failures;
- alerting on behavior changes rather than logging every invalid request verbosely.

## Review checklist

Before exposing a webhook receiver publicly, confirm:

- [ ] signature verification uses the raw request body;
- [ ] signature parsing rejects malformed values;
- [ ] constant-time comparison is used;
- [ ] HTTPS is enforced;
- [ ] request body size is bounded;
- [ ] accepted event types are allowlisted;
- [ ] repository/project identity is authorized after authentication;
- [ ] delivery IDs are persisted/claimed atomically;
- [ ] handlers are idempotent;
- [ ] queue retries are bounded;
- [ ] secrets and sensitive payloads are redacted/minimized in logs;
- [ ] downstream credentials use least privilege;
- [ ] secret rotation and incident handling are documented;
- [ ] monitoring covers invalid signatures, duplicate/retry behavior and worker failures.

A receiver that only checks HMAC may authenticate incoming bytes correctly while still being unsafe as an automation boundary. The complete design protects authenticity, replay behavior, authorization, availability and downstream side effects together.
