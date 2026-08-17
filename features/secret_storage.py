# -*- coding: utf-8 -*-
"""Windows user-bound storage for small application secrets."""

import base64
import os


_PREFIX = 'dpapi:v1:'


class SecretStorageError(RuntimeError):
    """Raised when a protected secret cannot be stored or restored."""


def protect_secret(value: str) -> str:
    """Protect *value* with Windows DPAPI for the current user account."""
    if not value:
        return ''
    if os.name != 'nt':
        raise SecretStorageError('DPAPI secret storage is only available on Windows')
    try:
        import win32crypt
        protected = win32crypt.CryptProtectData(
            value.encode('utf-8'), 'StickyNote WebDAV', None, None, None, 0
        )
        return _PREFIX + base64.urlsafe_b64encode(protected).decode('ascii')
    except Exception as exc:
        raise SecretStorageError('Unable to protect the secret with Windows DPAPI') from exc


def reveal_secret(value: str) -> str:
    """Restore a DPAPI value; return legacy plaintext for one-time migration."""
    if not value:
        return ''
    if not value.startswith(_PREFIX):
        return value
    if os.name != 'nt':
        raise SecretStorageError('DPAPI secret storage is only available on Windows')
    try:
        import win32crypt
        encoded = value[len(_PREFIX):].encode('ascii')
        raw = base64.urlsafe_b64decode(encoded)
        restored = win32crypt.CryptUnprotectData(raw, None, None, None, 0)[1]
        return restored.decode('utf-8')
    except Exception as exc:
        raise SecretStorageError('Unable to restore the protected secret') from exc
