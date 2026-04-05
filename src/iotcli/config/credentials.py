"""Fernet-encrypted credential vault — secrets never touch devices.yaml."""

from __future__ import annotations

import json
import os
from pathlib import Path

from cryptography.fernet import Fernet

# Fields that must be encrypted
SENSITIVE_FIELDS = frozenset({
    "token", "local_key", "password",
    "pat_token", "access_token", "refresh_token",
})


class CredentialVault:
    """Manages per-device encrypted credential files."""

    def __init__(self, config_dir: Path):
        self.credentials_dir = config_dir / "credentials"
        self.key_file = config_dir / ".key"
        self.credentials_dir.mkdir(parents=True, exist_ok=True)
        self._cipher = self._init_cipher()

    def _init_cipher(self) -> Fernet:
        if self.key_file.exists():
            key = self.key_file.read_bytes()
        else:
            key = Fernet.generate_key()
            self.key_file.write_bytes(key)
            os.chmod(self.key_file, 0o600)
        return Fernet(key)

    def _cred_path(self, device_name: str) -> Path:
        return self.credentials_dir / f"{device_name}.enc"

    def save(self, device_name: str, credentials: dict[str, str]) -> None:
        """Save (merge) credentials for a device."""
        existing = self.load(device_name)
        existing.update(credentials)
        # drop empty values
        existing = {k: v for k, v in existing.items() if v}
        encrypted = self._cipher.encrypt(json.dumps(existing).encode())
        path = self._cred_path(device_name)
        path.write_bytes(encrypted)
        os.chmod(path, 0o600)

    def load(self, device_name: str) -> dict[str, str]:
        """Load all credentials for a device."""
        path = self._cred_path(device_name)
        if not path.exists():
            return {}
        try:
            decrypted = self._cipher.decrypt(path.read_bytes())
            return json.loads(decrypted.decode())
        except Exception:
            return {}

    def delete(self, device_name: str) -> None:
        """Remove credential file for a device."""
        path = self._cred_path(device_name)
        if path.exists():
            path.unlink()

    @staticmethod
    def extract_secrets(data: dict) -> dict[str, str]:
        """Pull sensitive fields out of a flat dict."""
        return {k: str(data[k]) for k in SENSITIVE_FIELDS if data.get(k)}
