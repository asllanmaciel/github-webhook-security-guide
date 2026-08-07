<?php

declare(strict_types=1);

require __DIR__ . '/../examples/php/verify.php';

$secret = 'correct-horse-battery-staple';
$payload = '{"action":"opened"}';
$signature = 'sha256=' . hash_hmac('sha256', $payload, $secret);

assert(verifyGitHubWebhook($payload, $signature, $secret));
assert(!verifyGitHubWebhook($payload . 'tampered', $signature, $secret));
assert(!verifyGitHubWebhook($payload, '', $secret));

echo "PHP checks passed.\n";
