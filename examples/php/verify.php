<?php

declare(strict_types=1);

function verifyGitHubWebhook(string $payload, string $signatureHeader, string $secret): bool
{
    if ($secret === '' || !preg_match('/^sha256=[a-f0-9]{64}$/', $signatureHeader)) {
        return false;
    }

    $expected = 'sha256=' . hash_hmac('sha256', $payload, $secret);

    return hash_equals($expected, $signatureHeader);
}
