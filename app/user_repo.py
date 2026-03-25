"""All Postgres queries for users, google_accounts, and sync_items."""
from __future__ import annotations

from datetime import datetime
from uuid import UUID

from app.database import get_pool


# ── Users ────────────────────────────────────────────────────────────────────

async def get_user_by_id(user_id: str) -> dict | None:
    pool = await get_pool()
    row = await pool.fetchrow("SELECT * FROM users WHERE id = $1", UUID(user_id))
    return dict(row) if row else None


async def get_user_by_email(email: str) -> dict | None:
    pool = await get_pool()
    row = await pool.fetchrow("SELECT * FROM users WHERE email = $1", email)
    return dict(row) if row else None


async def get_user_by_sync_token(token: str) -> dict | None:
    pool = await get_pool()
    row = await pool.fetchrow("SELECT * FROM users WHERE sync_token = $1", token)
    return dict(row) if row else None


async def upsert_user(email: str, name: str) -> dict:
    """Create or update a user by email; return the full row."""
    pool = await get_pool()
    row = await pool.fetchrow(
        """
        INSERT INTO users (email, name)
        VALUES ($1, $2)
        ON CONFLICT (email) DO UPDATE
            SET name = EXCLUDED.name, updated_at = NOW()
        RETURNING *
        """,
        email,
        name,
    )
    return dict(row)


async def save_canvas_credentials(
    user_id: str, canvas_token_encrypted: str, canvas_domain: str
) -> None:
    pool = await get_pool()
    await pool.execute(
        """
        UPDATE users
        SET canvas_token_encrypted = $1, canvas_domain = $2, updated_at = NOW()
        WHERE id = $3
        """,
        canvas_token_encrypted,
        canvas_domain,
        UUID(user_id),
    )


# ── Google Accounts ───────────────────────────────────────────────────────────

async def get_google_account(user_id: str) -> dict | None:
    pool = await get_pool()
    row = await pool.fetchrow(
        "SELECT * FROM google_accounts WHERE user_id = $1", UUID(user_id)
    )
    return dict(row) if row else None


async def upsert_google_account(
    user_id: str,
    google_sub: str,
    email: str,
    access_token_encrypted: str,
    refresh_token_encrypted: str,
    token_expires_at: datetime | None,
    spreadsheet_id: str | None = None,
) -> dict:
    pool = await get_pool()
    row = await pool.fetchrow(
        """
        INSERT INTO google_accounts
            (user_id, google_sub, email, access_token_encrypted,
             refresh_token_encrypted, token_expires_at, spreadsheet_id)
        VALUES ($1, $2, $3, $4, $5, $6, $7)
        ON CONFLICT (user_id) DO UPDATE SET
            google_sub             = EXCLUDED.google_sub,
            email                  = EXCLUDED.email,
            access_token_encrypted = EXCLUDED.access_token_encrypted,
            refresh_token_encrypted = COALESCE(EXCLUDED.refresh_token_encrypted,
                                               google_accounts.refresh_token_encrypted),
            token_expires_at       = EXCLUDED.token_expires_at,
            spreadsheet_id         = COALESCE(EXCLUDED.spreadsheet_id,
                                              google_accounts.spreadsheet_id),
            updated_at             = NOW()
        RETURNING *
        """,
        UUID(user_id),
        google_sub,
        email,
        access_token_encrypted,
        refresh_token_encrypted,
        token_expires_at,
        spreadsheet_id,
    )
    return dict(row)


async def update_google_tokens(
    user_id: str,
    access_token_encrypted: str,
    token_expires_at: datetime | None,
) -> None:
    pool = await get_pool()
    await pool.execute(
        """
        UPDATE google_accounts
        SET access_token_encrypted = $1, token_expires_at = $2, updated_at = NOW()
        WHERE user_id = $3
        """,
        access_token_encrypted,
        token_expires_at,
        UUID(user_id),
    )


async def save_spreadsheet_id(user_id: str, spreadsheet_id: str) -> None:
    pool = await get_pool()
    await pool.execute(
        "UPDATE google_accounts SET spreadsheet_id = $1, updated_at = NOW() WHERE user_id = $2",
        spreadsheet_id,
        UUID(user_id),
    )


async def delete_google_account(user_id: str) -> None:
    pool = await get_pool()
    await pool.execute(
        "DELETE FROM google_accounts WHERE user_id = $1", UUID(user_id)
    )


# ── Sync Items (idempotency) ──────────────────────────────────────────────────

async def is_seen(user_id: str, item_key: str) -> bool:
    pool = await get_pool()
    row = await pool.fetchrow(
        "SELECT 1 FROM sync_items WHERE user_id = $1 AND item_key = $2",
        UUID(user_id),
        item_key,
    )
    return row is not None


async def mark_seen(user_id: str, item_key: str) -> None:
    pool = await get_pool()
    await pool.execute(
        """
        INSERT INTO sync_items (user_id, item_key)
        VALUES ($1, $2)
        ON CONFLICT (user_id, item_key) DO NOTHING
        """,
        UUID(user_id),
        item_key,
    )


async def bulk_seen(user_id: str, item_keys: list[str]) -> set[str]:
    """Return the subset of item_keys that have already been synced."""
    if not item_keys:
        return set()
    pool = await get_pool()
    rows = await pool.fetch(
        "SELECT item_key FROM sync_items WHERE user_id = $1 AND item_key = ANY($2)",
        UUID(user_id),
        item_keys,
    )
    return {r["item_key"] for r in rows}


async def bulk_mark_seen(user_id: str, item_keys: list[str]) -> None:
    if not item_keys:
        return
    pool = await get_pool()
    uid = UUID(user_id)
    await pool.executemany(
        "INSERT INTO sync_items (user_id, item_key) VALUES ($1, $2) ON CONFLICT DO NOTHING",
        [(uid, k) for k in item_keys],
    )
