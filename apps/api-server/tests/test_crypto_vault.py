"""Connector token vault. Implements: REQ-006, REQ-012."""

from uuid import uuid4

import pytest
from sqlalchemy import select

from app.core.crypto_vault import (
    TokenAccessDenied,
    TokenIntegrityError,
    TokenVault,
    read_connector_token,
    save_connector_token,
)
from app.db.models import User, UserConnectorToken
from app.db.session import get_session_factory


async def test_sealed_tokens_differ_each_write_and_only_the_owner_can_open_them() -> None:
    vault = TokenVault.from_settings()
    first = vault.seal("access-secret")
    second = vault.seal("access-secret")
    assert first != second
    assert b"access-secret" not in first
    assert vault.open(first) == "access-secret"
    tampered = bytearray(first)
    tampered[-1] ^= 0x01
    with pytest.raises(TokenIntegrityError):
        vault.open(bytes(tampered))

    async with get_session_factory()() as session:
        owner = User(email=f"vault-{uuid4().hex}@example.com", display_name="擁有者", department="RD")
        stranger = User(email=f"vault-{uuid4().hex}@example.com", display_name="其他人", department="RD")
        session.add_all([owner, stranger])
        await session.flush()
        await save_connector_token(
            session,
            owner_id=owner.id,
            provider="MICROSOFT_365",
            access_token="access-secret",
            refresh_token="refresh-secret",
            scopes=["Mail.Read"],
        )
        await session.flush()
        stored = await session.scalar(
            select(UserConnectorToken).where(UserConnectorToken.user_id == owner.id)
        )
        assert stored is not None
        assert b"access-secret" not in bytes(stored.encrypted_access_token)
        opened = await read_connector_token(
            session,
            actor_id=owner.id,
            owner_id=owner.id,
            provider="MICROSOFT_365",
        )
        assert opened.access_token == "access-secret"
        assert opened.refresh_token == "refresh-secret"
        assert opened.scopes == ["Mail.Read"]
        with pytest.raises(TokenAccessDenied):
            await read_connector_token(
                session,
                actor_id=stranger.id,
                owner_id=owner.id,
                provider="MICROSOFT_365",
            )
        stored.encrypted_access_token = bytes(tampered)
        await session.flush()
        with pytest.raises(TokenIntegrityError):
            await read_connector_token(
                session,
                actor_id=owner.id,
                owner_id=owner.id,
                provider="MICROSOFT_365",
            )
        await session.rollback()
