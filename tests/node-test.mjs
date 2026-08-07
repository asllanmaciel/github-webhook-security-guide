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

console.log("Node.js checks passed.");
