import { createHmac, timingSafeEqual } from "node:crypto";

export function verifyGitHubWebhook(payload, signatureHeader, secret) {
  if (!secret || !/^sha256=[a-f0-9]{64}$/.test(signatureHeader ?? "")) {
    return false;
  }

  const expected = `sha256=${createHmac("sha256", secret)
    .update(payload)
    .digest("hex")}`;
  const receivedBuffer = Buffer.from(signatureHeader, "utf8");
  const expectedBuffer = Buffer.from(expected, "utf8");

  return (
    receivedBuffer.length === expectedBuffer.length &&
    timingSafeEqual(receivedBuffer, expectedBuffer)
  );
}
