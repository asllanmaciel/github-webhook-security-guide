from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest

MODULE_PATH = Path(__file__).resolve().parents[1] / "examples" / "python" / "verify.py"
SPEC = importlib.util.spec_from_file_location("github_webhook_verify", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
verify_github_webhook = MODULE.verify_github_webhook


class VerifyGitHubWebhookTest(unittest.TestCase):
    def setUp(self) -> None:
        self.secret = "It's a Secret to Everybody"
        self.payload = b"Hello, World!"
        self.signature = (
            "sha256=757107ea0eb2509fc211221cce984b8a37570b6d7586c22c46f4379c8b043e17"
        )

    def test_accepts_github_documentation_vector(self) -> None:
        self.assertTrue(
            verify_github_webhook(self.payload, self.signature, self.secret)
        )

    def test_rejects_wrong_secret(self) -> None:
        self.assertFalse(
            verify_github_webhook(self.payload, self.signature, "wrong-secret")
        )

    def test_rejects_tampered_payload(self) -> None:
        self.assertFalse(
            verify_github_webhook(
                self.payload + b"tampered",
                self.signature,
                self.secret,
            )
        )

    def test_rejects_missing_or_malformed_signatures(self) -> None:
        invalid_signatures = (
            None,
            "",
            "sha1=" + "a" * 40,
            "sha256=not-hex",
            "sha256=" + "A" * 64,
            "sha256=" + "a" * 63,
        )

        for signature in invalid_signatures:
            with self.subTest(signature=signature):
                self.assertFalse(
                    verify_github_webhook(self.payload, signature, self.secret)
                )

    def test_rejects_empty_secret(self) -> None:
        self.assertFalse(verify_github_webhook(self.payload, self.signature, ""))


if __name__ == "__main__":
    unittest.main()
