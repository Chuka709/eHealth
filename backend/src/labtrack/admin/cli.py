"""`just create-admin <username>`: an operator creates an admin account (docs/04 §1).

Runs as the schema owner (MIGRATION_DATABASE_URL, the `migrate` container) because admins are
never created through the API. The admin types their own password; the TOTP secret is shown
once, must be confirmed with a code, and is stored only envelope-encrypted.
"""

import asyncio
import getpass
import sys
from collections.abc import Callable
from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import create_async_engine

from labtrack.core.envelope import field_aad, new_dek, parse
from labtrack.core.security import hash_password, password_problems
from labtrack.core.totp import matching_step, new_secret, provisioning_uri
from labtrack.db.sql import bound_text
from labtrack.keys import KeyProvider, decrypt_field, encrypt_field, get_key_provider
from labtrack.user_keys import seal_for_user, unwrap_user_key, wrap_user_key

ADMIN_ROLES = ("super_admin", "support")


class AdminExistsError(Exception):
    pass


async def create_admin(
    url: str,
    provider: KeyProvider,
    *,
    username: str,
    display_name: str,
    role: str,
    password_hash: str,
    totp_secret: str,
) -> UUID:
    if role not in ADMIN_ROLES:
        raise ValueError("role must be super_admin or support")
    uid = uuid4()
    secret_enc = await encrypt_field(
        provider, totp_secret, field_aad("users", "totp_secret_enc", uid)
    )
    engine = create_async_engine(url, hide_parameters=True)
    try:
        async with engine.connect() as conn, conn.begin():
            exists = (
                await conn.execute(
                    bound_text("select exists (select 1 from users where username = :u)"),
                    {"u": username},
                )
            ).scalar_one()
            if exists:
                raise AdminExistsError(username)
            await conn.execute(
                bound_text(
                    "insert into users (id, username, display_name, role, account_status,"
                    " password_hash, password_changed_at, totp_secret_enc)"
                    " values (:id, :u, :n, cast(:r as user_role), 'active', :pw, now(), :totp)"
                ),
                {
                    "id": uid,
                    "u": username,
                    "n": display_name,
                    "r": role,
                    "pw": password_hash,
                    "totp": secret_enc,
                },
            )
            await conn.execute(
                bound_text(
                    "insert into audit_logs (actor_role, action, target_user_id, entity,"
                    " entity_id, diff) values ('cli', 'admin.admin_create', :id, 'user',"
                    " :eid, jsonb_build_object('role', cast(:r as text)))"
                ),
                {"id": uid, "eid": str(uid), "r": role},
            )
    finally:
        await engine.dispose()
    return uid


def run(
    url: str,
    username: str,
    role: str,
    *,
    ask: Callable[[str], str] = input,
    ask_secret: Callable[[str], str] = getpass.getpass,
    out: Callable[[str], object] = sys.stdout.write,
) -> int:
    display_name = ask("Display name: ").strip()
    if not 1 <= len(display_name) <= 100:  # noqa: PLR2004 - users.display_name check
        out("display name must be 1-100 characters\n")
        return 1
    password = ask_secret("Password: ")
    if ask_secret("Repeat password: ") != password:
        out("passwords differ\n")
        return 1
    problems = password_problems(password, username, display_name)
    if problems:
        out(f"password rejected: {', '.join(problems)}\n")
        return 1
    secret = new_secret()
    out(
        "Add this account to an authenticator app (shown once):\n"
        f"  {provisioning_uri(secret, username)}\n"
        f"  manual key: {secret}\n"
    )
    code = ask("Code from the app: ").strip()
    if matching_step(secret, code, datetime.now(UTC)) is None:
        out("code does not match - nothing was created\n")
        return 1
    try:
        uid = asyncio.run(
            create_admin(
                url,
                get_key_provider(),
                username=username,
                display_name=display_name,
                role=role,
                password_hash=hash_password(password),
                totp_secret=secret,
            )
        )
    except AdminExistsError:
        out("username already exists - nothing was created\n")
        return 1
    out(f"created {role} {uid}\n")
    return 0


async def unlock_admin(url: str, username: str) -> bool:
    """Clear an admin's sign-in lockout (admins cannot unlock each other through the API)."""
    engine = create_async_engine(url, hide_parameters=True)
    try:
        async with engine.connect() as conn, conn.begin():
            uid = (
                await conn.execute(
                    bound_text(
                        "select id from users where username = :u"
                        " and role in ('super_admin','support')"
                    ),
                    {"u": username},
                )
            ).scalar_one_or_none()
            if uid is None:
                return False
            await conn.execute(
                bound_text(
                    "insert into auth_attempts (kind, username, success)"
                    " values ('admin_login', :u, true)"
                ),
                {"u": username},
            )
            await conn.execute(
                bound_text(
                    "insert into audit_logs (actor_role, action, target_user_id, entity,"
                    " entity_id) values ('cli', 'admin.admin_unlock', :id, 'user', :eid)"
                ),
                {"id": uid, "eid": str(uid)},
            )
    finally:
        await engine.dispose()
    return True


async def rewrap_user_fields(url: str, provider: KeyProvider) -> int:
    """Moves phone numbers sealed under the service KEK (before migration 0008) under their
    user's own key, so purging an account shreds them too. Idempotent; returns how many."""
    engine = create_async_engine(url, hide_parameters=True)
    moved = 0
    try:
        async with engine.connect() as conn, conn.begin():
            rows = (
                await conn.execute(
                    bound_text(
                        "select id, contact_phone_enc from users"
                        " where contact_phone_enc is not null for update"
                    )
                )
            ).all()
            for row in rows:
                if parse(bytes(row.contact_phone_enc)).kek_id.startswith("u:"):
                    continue
                aad = field_aad("users", "contact_phone_enc", row.id)
                phone = await decrypt_field(provider, bytes(row.contact_phone_enc), aad)
                stored = (
                    await conn.execute(
                        bound_text("select wrapped_key from user_keys where user_id = :u"),
                        {"u": row.id},
                    )
                ).scalar_one_or_none()
                if stored is None:
                    key = new_dek()
                    await conn.execute(
                        bound_text("insert into user_keys (user_id, wrapped_key) values (:u, :w)"),
                        {"u": row.id, "w": await wrap_user_key(provider, row.id, key)},
                    )
                else:
                    key = await unwrap_user_key(provider, row.id, bytes(stored))
                await conn.execute(
                    bound_text("update users set contact_phone_enc = :b where id = :u"),
                    {"u": row.id, "b": await seal_for_user(row.id, key, phone, aad)},
                )
                moved += 1
    finally:
        await engine.dispose()
    return moved
