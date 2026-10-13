import asyncio
import hashlib
from datetime import UTC, datetime, timedelta

import jwt
import pytest
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.core.config import settings
from app.core.security import PasswordHasher
from app.models import User
from app.models.auth_session import AuthSession, RefreshToken
from app.repositories.auth_session import AuthSessionRepository


async def register_and_login(client, username="alice"):
    payload = {"username": username, "password": "strong-password123"}
    registered = await client.post("/api/v1/auth/register", json=payload)
    assert registered.status_code == 201, registered.text
    assert "password_hash" not in registered.json()
    logged_in = await client.post("/api/v1/auth/login", json=payload)
    assert logged_in.status_code == 200, logged_in.text
    pair = logged_in.json()
    assert pair["token_type"] == "bearer"
    assert pair["access_token"] and pair["refresh_token"]
    assert pair["access_token"] != pair["refresh_token"]
    return pair


async def me(client, pair):
    return await client.get(
        "/api/v1/users/me", headers={"Authorization": "Bearer " + pair["access_token"]}
    )


async def refresh(client, token):
    return await client.post("/api/v1/auth/refresh", json={"refresh_token": token})


async def test_real_password_jwt_rotation_replay(api_client, database_engine) -> None:
    first = await register_and_login(api_client)
    factory = async_sessionmaker(database_engine, expire_on_commit=False)
    async with factory() as session:
        user = (await session.scalars(select(User))).one()
        assert user.password_hash != "strong-password123"
        assert PasswordHasher().verify_password(
            "strong-password123", user.password_hash
        )
        assert not PasswordHasher().verify_password("incorrect", user.password_hash)
        stored = (await session.scalars(select(RefreshToken))).one()
        assert (
            stored.token_hash
            == hashlib.sha256(first["refresh_token"].encode()).hexdigest()
        )
        assert stored.token_hash != first["refresh_token"]
    assert (await me(api_client, first)).status_code == 200
    rotated = await refresh(api_client, first["refresh_token"])
    assert rotated.status_code == 200, rotated.text
    second = rotated.json()
    assert second["refresh_token"] != first["refresh_token"]
    assert (await me(api_client, second)).status_code == 200
    assert (await refresh(api_client, first["refresh_token"])).status_code == 401
    assert (await refresh(api_client, second["refresh_token"])).status_code == 401
    assert (await me(api_client, second)).status_code == 401


async def test_logout_is_idempotent_and_does_not_revoke_other_login(api_client) -> None:
    first = await register_and_login(api_client)
    response = await api_client.post(
        "/api/v1/auth/login",
        json={
            "username": "alice",
            "password": "strong-password123",
        },
    )
    assert response.status_code == 200
    independent = response.json()
    for _ in range(2):
        response = await api_client.post(
            "/api/v1/auth/logout", json={"refresh_token": first["refresh_token"]}
        )
        assert response.status_code == 204
        assert response.content == b""
    assert (await me(api_client, first)).status_code == 401
    assert (await refresh(api_client, first["refresh_token"])).status_code == 401
    assert (await me(api_client, independent)).status_code == 200
    assert (await refresh(api_client, independent["refresh_token"])).status_code == 200


async def test_unknown_refresh_and_logout_do_not_revoke_valid_session(
    api_client,
) -> None:
    pair = await register_and_login(api_client)
    assert (await refresh(api_client, "unknown-refresh-secret")).status_code == 401
    response = await api_client.post(
        "/api/v1/auth/logout", json={"refresh_token": "unknown-refresh-secret"}
    )
    assert response.status_code == 204
    assert (await me(api_client, pair)).status_code == 200
    assert (await refresh(api_client, pair["refresh_token"])).status_code == 200


async def test_concurrent_refresh_cannot_create_two_valid_pairs(api_client) -> None:
    pair = await register_and_login(api_client)
    barrier = asyncio.Barrier(2)

    async def simultaneous_refresh():
        await barrier.wait()
        return await refresh(api_client, pair["refresh_token"])

    responses = await asyncio.gather(simultaneous_refresh(), simultaneous_refresh())
    assert sorted(response.status_code for response in responses) == [200, 401]
    winner = next(
        response.json() for response in responses if response.status_code == 200
    )
    # The losing replay revokes the family, including the racing winner.
    assert (await refresh(api_client, winner["refresh_token"])).status_code == 401
    assert (await me(api_client, winner)).status_code == 401


@pytest.mark.parametrize("bad_kind", ["signature", "expired", "refresh_type", "no_sid"])
async def test_real_access_token_validation(api_client, bad_kind) -> None:
    pair = await register_and_login(api_client)
    secret = settings.jwt_secret_key.get_secret_value()
    payload = jwt.decode(pair["access_token"], secret, algorithms=["HS256"])
    if bad_kind == "expired":
        payload["exp"] = datetime.now(UTC) - timedelta(seconds=1)
    elif bad_kind == "refresh_type":
        payload["type"] = "refresh"
    elif bad_kind == "no_sid":
        payload.pop("sid")
    token = jwt.encode(
        payload,
        "wrong-signing-secret-at-least-32-chars" if bad_kind == "signature" else secret,
        algorithm="HS256",
    )
    response = await me(api_client, {"access_token": token})
    assert response.status_code == 401


@pytest.mark.parametrize(
    "username,password",
    [
        ("alice", "wrong-password"),
        ("missing", "strong-password123"),
    ],
)
async def test_login_rejects_wrong_credentials(api_client, username, password) -> None:
    await register_and_login(api_client)
    response = await api_client.post(
        "/api/v1/auth/login",
        json={
            "username": username,
            "password": password,
        },
    )
    assert response.status_code == 401


async def test_readiness_with_real_database(api_client) -> None:
    response = await api_client.get("/api/v1/health/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_expired_session_rejects_access_and_refresh(api_client, database_engine):
    pair = await register_and_login(api_client)
    factory = async_sessionmaker(database_engine, expire_on_commit=False)
    async with factory() as session:
        auth_session = (await session.scalars(select(AuthSession))).one()
        auth_session.expires_at = datetime.now(UTC) - timedelta(seconds=1)
        await session.commit()
    assert (await refresh(api_client, pair["refresh_token"])).status_code == 401
    assert (await me(api_client, pair)).status_code == 401


async def test_inactive_user_cannot_login_refresh_or_use_access(
    api_client, database_engine
):
    pair = await register_and_login(api_client)
    factory = async_sessionmaker(database_engine, expire_on_commit=False)
    async with factory() as session:
        user = (await session.scalars(select(User))).one()
        user.is_active = False
        await session.commit()
    response = await api_client.post(
        "/api/v1/auth/login",
        json={
            "username": "alice",
            "password": "strong-password123",
        },
    )
    assert response.status_code == 401
    assert (await refresh(api_client, pair["refresh_token"])).status_code == 401
    assert (await me(api_client, pair)).status_code == 401


async def test_refresh_does_not_extend_absolute_expiry(api_client, database_engine):
    pair = await register_and_login(api_client)
    factory = async_sessionmaker(database_engine, expire_on_commit=False)
    expiry = datetime.now(UTC) + timedelta(minutes=10)
    async with factory() as session:
        auth_session = (await session.scalars(select(AuthSession))).one()
        auth_session.expires_at = expiry
        await session.commit()
    assert (await refresh(api_client, pair["refresh_token"])).status_code == 200
    async with factory() as session:
        auth_session = (await session.scalars(select(AuthSession))).one()
        assert auth_session.expires_at == expiry


async def test_cross_user_session_claim_is_rejected(api_client):
    first = await register_and_login(api_client)
    second = await register_and_login(api_client, username="bob")
    secret = settings.jwt_secret_key.get_secret_value()
    payload = jwt.decode(first["access_token"], secret, algorithms=["HS256"])
    other_payload = jwt.decode(second["access_token"], secret, algorithms=["HS256"])
    payload["sid"] = other_payload["sid"]
    forged = jwt.encode(payload, secret, algorithm="HS256")
    assert (await me(api_client, {"access_token": forged})).status_code == 401


async def test_logout_consumed_refresh_revokes_current_pair(api_client):
    first = await register_and_login(api_client)
    rotated = await refresh(api_client, first["refresh_token"])
    assert rotated.status_code == 200
    second = rotated.json()
    response = await api_client.post(
        "/api/v1/auth/logout", json={"refresh_token": first["refresh_token"]}
    )
    assert response.status_code == 204
    assert (await me(api_client, second)).status_code == 401
    assert (await refresh(api_client, second["refresh_token"])).status_code == 401


async def test_failed_rotation_rolls_back_token_consumption(
    api_client, database_engine, monkeypatch
):
    first = await register_and_login(api_client)
    add_token = AuthSessionRepository.add_refresh_token

    async def fail_after_insert(repo, token):
        await add_token(repo, token)
        raise SQLAlchemyError("injected failure after token flush")

    with monkeypatch.context() as patch:
        patch.setattr(AuthSessionRepository, "add_refresh_token", fail_after_insert)
        with pytest.raises(SQLAlchemyError, match="injected failure"):
            await refresh(api_client, first["refresh_token"])
    factory = async_sessionmaker(database_engine)
    async with factory() as session:
        tokens = (await session.scalars(select(RefreshToken))).all()
        assert len(tokens) == 1
        assert tokens[0].used_at is None
        family = (await session.scalars(select(AuthSession))).one()
        assert family.revoked_at is None
    assert (await refresh(api_client, first["refresh_token"])).status_code == 200
