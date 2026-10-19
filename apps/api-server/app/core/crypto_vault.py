"""AES-256-GCM vault for per-user connector tokens. Implements: REQ-006, REQ-012."""

import base64
import os
from dataclasses import dataclass
from uuid import UUID

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.models import UserConnectorToken

_NONCE_BYTES = 12


class TokenIntegrityError(Exception):
    """Ciphertext or nonce failed AES-GCM authentication."""


class TokenAccessDenied(Exception):
    """The caller is not the owner of the connector token."""


@dataclass(frozen=True)
class ConnectorSecrets:
    access_token: str
    refresh_token: str | None
    scopes: list[str]


class TokenVault:
    def __init__(self, key: bytes) -> None:
        if len(key) != 32:
            raise ValueError("AES-256-GCM 需要 32 byte 金鑰")
        self._aes = AESGCM(key)

    @classmethod
    def from_settings(cls) -> "TokenVault":
        key = base64.b64decode(settings.TOKEN_VAULT_KEY)
        return cls(key)

    def seal(self, plaintext: str) -> bytes:
        nonce = os.urandom(_NONCE_BYTES)
        ciphertext = self._aes.encrypt(nonce, plaintext.encode("utf-8"), None)
        return nonce + ciphertext

    def open(self, blob: bytes) -> str:
        if len(blob) <= _NONCE_BYTES:
            raise TokenIntegrityError("權杖密文不完整")
        nonce, ciphertext = blob[:_NONCE_BYTES], blob[_NONCE_BYTES:]
        try:
            return self._aes.decrypt(nonce, ciphertext, None).decode("utf-8")
        except InvalidTag as exc:
            raise TokenIntegrityError("權杖密文驗證失敗") from exc


async def save_connector_token(
    db: AsyncSession,
    *,
    owner_id: UUID,
    provider: str,
    access_token: str,
    refresh_token: str | None,
    scopes: list[str],
) -> None:
    vault = TokenVault.from_settings()
    values = {
        "user_id": owner_id,
        "provider": provider,
        "encrypted_access_token": vault.seal(access_token),
        "encrypted_refresh_token": None if refresh_token is None else vault.seal(refresh_token),
        "scopes": scopes,
    }
    await db.execute(
        insert(UserConnectorToken)
        .values(**values)
        .on_conflict_do_update(
            index_elements=["user_id", "provider"],
            set_={
                "encrypted_access_token": values["encrypted_access_token"],
                "encrypted_refresh_token": values["encrypted_refresh_token"],
                "scopes": scopes,
            },
        )
    )


async def read_connector_token(
    db: AsyncSession,
    *,
    actor_id: UUID,
    owner_id: UUID,
    provider: str,
) -> ConnectorSecrets:
    if actor_id != owner_id:
        raise TokenAccessDenied("僅能讀取自己的連接器權杖")
    row = await db.scalar(
        select(UserConnectorToken).where(
            UserConnectorToken.user_id == owner_id,
            UserConnectorToken.provider == provider,
        )
    )
    if row is None:
        raise TokenAccessDenied("找不到連接器權杖")
    vault = TokenVault.from_settings()
    refresh = None if row.encrypted_refresh_token is None else vault.open(bytes(row.encrypted_refresh_token))
    return ConnectorSecrets(
        access_token=vault.open(bytes(row.encrypted_access_token)),
        refresh_token=refresh,
        scopes=[str(item) for item in row.scopes],
    )
