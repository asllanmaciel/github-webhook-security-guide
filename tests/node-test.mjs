import { createHmac } from "node:crypto";
import { strict as assert } from "node:assert";
import { verifyGitHubWebhook } from "../examples/node/verify.mjs";

const secret = "correct-horse-battery-staple";
const payload = '{"action":"opened"}';
const signature = `sha256=${createHmac("sha256", secret)
  .update(payload)
  .digest("hex")}`;

assert.equal(verifyGitHubWebhook(payload, signature, secret), true);
assert.equal(verifyGitHubWebhook(`${payload}tampered`, signature, secret), false);
assert.equal(verifyGitHubWebhook(payload, "", secret), false);
assert.equal(
  verifyGitHubWebhook(payload, `sha1=${"a".repeat(40)}`, secret),
  false
);
assert.equal(verifyGitHubWebhook(payload, "sha256=not-hex", secret), false);
assert.equal(verifyGitHubWebhook(payload, signature, ""), false);

console.log("Node.js checks passed.");
