import os
import asyncpg
from asyncpg import Pool
from typing import Optional
import logging

logger = logging.getLogger(__name__)


class Database:
    def __init__(self):
        self.pool: Optional[Pool] = None

    async def connect(self):
        database_url = os.getenv('DATABASE_URL')
        if not database_url:
            raise ValueError("DATABASE_URL environment variable not set")
        
        self.pool = await asyncpg.create_pool(
            database_url,
            min_size=5,
            max_size=20,
            command_timeout=60
        )
        logger.info("Database pool created successfully")
        await self.initialize_schema()

    async def disconnect(self):
        if self.pool:
            await self.pool.close()
            logger.info("Database pool closed")

    async def initialize_schema(self):
        async with self.pool.acquire() as conn:
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS live_sessions (
                    id SERIAL PRIMARY KEY,
                    session_id INTEGER,
                    tiktok_username TEXT NOT NULL,
                    started_at TIMESTAMPTZ DEFAULT NOW(),
                    ended_at TIMESTAMPTZ,
                    status TEXT DEFAULT 'active'
                );
            ''')

            await conn.execute('''
                CREATE TABLE IF NOT EXISTS tiktok_accounts (
                    handle_id SERIAL PRIMARY KEY,
                    handle_name TEXT UNIQUE NOT NULL,
                    first_seen TIMESTAMPTZ DEFAULT NOW(),
                    last_seen TIMESTAMPTZ DEFAULT NOW(),
                    linked_discord_id BIGINT,
                    points INTEGER DEFAULT 0 NOT NULL,
                    last_known_level INTEGER DEFAULT 0
                );
            ''')

            await conn.execute('''
                CREATE TABLE IF NOT EXISTS tiktok_interactions (
                    id SERIAL PRIMARY KEY,
                    session_id INTEGER REFERENCES live_sessions(id) ON DELETE CASCADE,
                    tiktok_account_id INTEGER REFERENCES tiktok_accounts(handle_id) ON DELETE SET NULL,
                    interaction_type TEXT NOT NULL,
                    value TEXT,
                    coin_value INTEGER,
                    user_level INTEGER,
                    timestamp TIMESTAMPTZ DEFAULT NOW()
                );
            ''')

            await conn.execute('''
                CREATE TABLE IF NOT EXISTS viewer_count_snapshots (
                    id SERIAL PRIMARY KEY,
                    session_id INTEGER REFERENCES live_sessions(id) ON DELETE CASCADE,
                    viewer_count INTEGER NOT NULL,
                    timestamp TIMESTAMPTZ DEFAULT NOW()
                );
            ''')

            await conn.execute('''
                CREATE TABLE IF NOT EXISTS submissions (
                    id SERIAL PRIMARY KEY,
                    public_id TEXT UNIQUE NOT NULL,
                    user_id BIGINT NOT NULL,
                    username TEXT NOT NULL,
                    artist_name TEXT NOT NULL,
                    song_name TEXT NOT NULL,
                    link_or_file TEXT,
                    queue_line TEXT,
                    submission_time TIMESTAMPTZ DEFAULT NOW(),
                    played_time TIMESTAMPTZ,
                    note TEXT,
                    tiktok_username TEXT,
                    total_score REAL DEFAULT 0
                );
            ''')

            await conn.execute('''
                CREATE TABLE IF NOT EXISTS user_points (
                    user_id BIGINT PRIMARY KEY,
                    points INTEGER DEFAULT 0 NOT NULL
                );
            ''')

            await conn.execute('''
                CREATE TABLE IF NOT EXISTS bot_config (
                    key TEXT PRIMARY KEY,
                    value TEXT,
                    channel_id BIGINT,
                    message_id BIGINT
                );
            ''')

            await conn.execute('''
                CREATE TABLE IF NOT EXISTS persistent_embeds (
                    id SERIAL PRIMARY KEY,
                    embed_type TEXT NOT NULL,
                    channel_id BIGINT NOT NULL,
                    message_id BIGINT NOT NULL,
                    current_page INTEGER DEFAULT 0,
                    last_content_hash TEXT,
                    last_updated TIMESTAMPTZ DEFAULT NOW(),
                    is_active BOOLEAN DEFAULT TRUE,
                    UNIQUE (embed_type, channel_id)
                );
            ''')

            await conn.execute('''
                CREATE TABLE IF NOT EXISTS queue_config (
                    queue_line TEXT PRIMARY KEY,
                    channel_id BIGINT,
                    pinned_message_id BIGINT
                );
            ''')

            await conn.execute('''
                CREATE TABLE IF NOT EXISTS luxury_coins (
                    user_id BIGINT PRIMARY KEY,
                    balance INTEGER DEFAULT 0 NOT NULL
                );
            ''')

            await conn.execute('''
                CREATE TABLE IF NOT EXISTS tiktok_watch_time (
                    id SERIAL PRIMARY KEY,
                    session_id INTEGER REFERENCES live_sessions(id) ON DELETE CASCADE,
                    tiktok_account_id INTEGER REFERENCES tiktok_accounts(handle_id) ON DELETE SET NULL,
                    linked_discord_id BIGINT,
                    watch_seconds INTEGER DEFAULT 0 NOT NULL,
                    last_updated TIMESTAMPTZ DEFAULT NOW()
                );
            ''')

            await self._create_indexes(conn)
            logger.info("Database schema initialized successfully")

    async def _create_indexes(self, conn):
        indexes = [
            'CREATE INDEX IF NOT EXISTS idx_submissions_user_id ON submissions(user_id);',
            'CREATE INDEX IF NOT EXISTS idx_submissions_queue_line ON submissions(queue_line);',
            'CREATE INDEX IF NOT EXISTS idx_submissions_played_time ON submissions(played_time);',
            'CREATE INDEX IF NOT EXISTS idx_submissions_submission_time ON submissions(submission_time);',
            'CREATE INDEX IF NOT EXISTS idx_tiktok_interactions_session_id ON tiktok_interactions(session_id);',
            'CREATE INDEX IF NOT EXISTS idx_tiktok_interactions_tiktok_account_id ON tiktok_interactions(tiktok_account_id);',
            'CREATE INDEX IF NOT EXISTS idx_tiktok_accounts_linked_discord_id ON tiktok_accounts(linked_discord_id);',
            'CREATE INDEX IF NOT EXISTS idx_tiktok_handles_search ON tiktok_accounts(handle_name text_pattern_ops);',
        ]

        for index_sql in indexes:
            await conn.execute(index_sql)

        await conn.execute('''
            CREATE INDEX IF NOT EXISTS idx_submissions_free_queue 
            ON submissions(queue_line, total_score DESC, submission_time ASC) 
            WHERE queue_line = 'Free';
        ''')

        await conn.execute('''
            CREATE INDEX IF NOT EXISTS idx_tiktok_handles_unlinked 
            ON tiktok_accounts(linked_discord_id) 
            WHERE linked_discord_id IS NULL;
        ''')

    async def execute(self, query: str, *args):
        async with self.pool.acquire() as conn:
            return await conn.execute(query, *args)

    async def fetch(self, query: str, *args):
        async with self.pool.acquire() as conn:
            return await conn.fetch(query, *args)

    async def fetchrow(self, query: str, *args):
        async with self.pool.acquire() as conn:
            return await conn.fetchrow(query, *args)

    async def fetchval(self, query: str, *args):
        async with self.pool.acquire() as conn:
            return await conn.fetchval(query, *args)


db = Database()
