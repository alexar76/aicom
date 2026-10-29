"""Remove the configured provider credential from diagnostics and streamed echoes."""

from __future__ import annotations


def redact_credential(text: str, credential: str) -> str:
    return text.replace(credential, "[redacted]") if credential else text


class CredentialStreamRedactor:
    """Hold only a suffix that might become the credential in the next chunk."""

    def __init__(self, credential: str):
        self.credential = credential
        self.pending = ""

    def feed(self, text: str) -> str:
        if not self.credential:
            return text
        combined = redact_credential(self.pending + text, self.credential)
        keep = 0
        for length in range(min(len(combined), len(self.credential) - 1), 0, -1):
            if self.credential.startswith(combined[-length:]):
                keep = length
                break
        if keep:
            self.pending = combined[-keep:]
            return combined[:-keep]
        self.pending = ""
        return combined

    def finish(self) -> str:
        remaining = redact_credential(self.pending, self.credential)
        self.pending = ""
        return remaining
