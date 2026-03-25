"""asyncpg connection pool for multi-tenant Postgres (Neon)."""
import asyncpg

from app.config import settings

_pool: asyncpg.Pool | None = None


def _clean_dsn(url: str) -> str:
    """Strip params asyncpg doesn't support (e.g. channel_binding)."""
    if "channel_binding" not in url:
        return url
    parts = url.split("?", 1)
    if len(parts) == 1:
        return url
    base = parts[0]
    params = [p for p in parts[1].split("&") if not p.startswith("channel_binding")]
    return f"{base}?{'&'.join(params)}" if params else base


async def get_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(_clean_dsn(settings.database_url), ssl="require")
    return _pool


async def close_pool() -> None:
    global _pool
    if _pool:
        await _pool.close()
        _pool = None
