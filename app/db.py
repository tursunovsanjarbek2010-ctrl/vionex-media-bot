import asyncpg
from .config import settings

_pool = None

async def connect():
    global _pool
    _pool = await asyncpg.create_pool(
        settings.database_url,
        min_size=1,
        max_size=5
    )

    async with _pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id BIGINT PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                joined_at TIMESTAMPTZ DEFAULT NOW(),
                last_seen TIMESTAMPTZ DEFAULT NOW()
            );

            CREATE TABLE IF NOT EXISTS downloads (
                id BIGSERIAL PRIMARY KEY,
                user_id BIGINT NOT NULL,
                source_host TEXT,
                media_type TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TIMESTAMPTZ DEFAULT NOW()
            );
        """)

async def close():
    if _pool:
        await _pool.close()

async def touch_user(user):
    async with _pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO users(user_id, username, first_name)
            VALUES($1, $2, $3)
            ON CONFLICT(user_id) DO UPDATE SET
                username = EXCLUDED.username,
                first_name = EXCLUDED.first_name,
                last_seen = NOW()
        """, user.id, user.username, user.first_name)

async def log_download(user_id, host, media_type, status):
    async with _pool.acquire() as conn:
        await conn.execute(
            """INSERT INTO downloads
            (user_id, source_host, media_type, status)
            VALUES($1, $2, $3, $4)""",
            user_id, host, media_type, status
        )

async def get_stats():
    async with _pool.acquire() as conn:
        users = await conn.fetchval(
            "SELECT COUNT(*) FROM users"
        )
        total = await conn.fetchval(
            "SELECT COUNT(*) FROM downloads"
        )
        success = await conn.fetchval(
            "SELECT COUNT(*) FROM downloads WHERE status='success'"
        )
        return users, total, success
