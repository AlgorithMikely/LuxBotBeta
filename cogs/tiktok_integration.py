import discord
from discord.ext import commands, tasks
from discord import app_commands
from TikTokLive import TikTokLiveClient
from TikTokLive.events import ConnectEvent, DisconnectEvent, LiveEndEvent, GiftEvent, JoinEvent, LikeEvent, CommentEvent, ShareEvent, FollowEvent, RoomUserSeqEvent
import logging
from database import db
from typing import Optional
import asyncio

logger = logging.getLogger(__name__)


class TikTokIntegration(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.client: Optional[TikTokLiveClient] = None
        self.session_id: Optional[int] = None
        self.persistent_connection = False
        self.username = None
        self.gift_streaks = {}
        self.active_session_id = None

    async def get_or_create_tiktok_account(self, handle_name: str, user_level: int = 0):
        row = await db.fetchrow(
            'SELECT * FROM tiktok_accounts WHERE handle_name = $1',
            handle_name
        )

        if row:
            await db.execute(
                'UPDATE tiktok_accounts SET last_seen = NOW(), last_known_level = $1 WHERE handle_name = $2',
                user_level, handle_name
            )
            return row['handle_id']
        else:
            handle_id = await db.fetchval(
                'INSERT INTO tiktok_accounts (handle_name, last_known_level) VALUES ($1, $2) RETURNING handle_id',
                handle_name, user_level
            )
            return handle_id

    async def log_interaction(self, tiktok_account_id: int, interaction_type: str,
                             value: str = None, coin_value: int = None, user_level: int = 0):
        if self.session_id:
            await db.execute('''
                INSERT INTO tiktok_interactions 
                (session_id, tiktok_account_id, interaction_type, value, coin_value, user_level)
                VALUES ($1, $2, $3, $4, $5, $6)
            ''', self.session_id, tiktok_account_id, interaction_type, value, coin_value, user_level)

    async def process_gift(self, gift_event):
        user = gift_event.user
        gift = gift_event.gift

        handle_id = await self.get_or_create_tiktok_account(user.unique_id, getattr(user, 'level', 0))

        is_streaking = getattr(gift_event, 'streaking', False)

        if is_streaking:
            streak_key = f"{user.unique_id}_{gift.id}"
            self.gift_streaks[streak_key] = gift_event
            return

        streak_key = f"{user.unique_id}_{gift.id}"
        if streak_key in self.gift_streaks:
            del self.gift_streaks[streak_key]

        diamond_count = gift.diamond_count * gift_event.repeat_count

        if diamond_count < 1000:
            points = diamond_count * 2
        else:
            points = diamond_count

        await db.execute(
            'UPDATE tiktok_accounts SET points = points + $1 WHERE handle_id = $2',
            points, handle_id
        )

        await self.log_interaction(handle_id, 'gift', gift.name, diamond_count, getattr(user, 'level', 0))

        linked_discord_id = await db.fetchval(
            'SELECT linked_discord_id FROM tiktok_accounts WHERE handle_id = $1',
            handle_id
        )

        if linked_discord_id:
            await db.execute(
                'INSERT INTO user_points (user_id, points) VALUES ($1, $2) ON CONFLICT (user_id) DO UPDATE SET points = user_points.points + $2',
                linked_discord_id, points
            )

        submission = await db.fetchrow('''
            SELECT * FROM submissions
            WHERE user_id = $1 AND queue_line IN ('Free', 'Pending Skips')
            ORDER BY submission_time DESC
            LIMIT 1
        ''', linked_discord_id or 0)

        if submission and linked_discord_id:
            total_gifts = await db.fetchval('''
                SELECT COALESCE(SUM(coin_value), 0) FROM tiktok_interactions
                WHERE tiktok_account_id = $1 AND interaction_type = 'gift'
                AND session_id = $2
            ''', handle_id, self.session_id)

            new_queue = None
            if total_gifts >= 6000:
                new_queue = '25+ Skip'
            elif total_gifts >= 5000:
                new_queue = '20 Skip'
            elif total_gifts >= 4000:
                new_queue = '15 Skip'
            elif total_gifts >= 2000:
                new_queue = '10 Skip'
            elif total_gifts >= 1000:
                new_queue = '5 Skip'

            if new_queue and new_queue != submission['queue_line']:
                await db.execute(
                    'UPDATE submissions SET queue_line = $1 WHERE id = $2',
                    new_queue, submission['id']
                )
                self.bot.dispatch('queue_update')
                logger.info(f"Moved submission {submission['public_id']} to {new_queue}")

    async def end_active_session(self):
        """End active session and return session data for immediate use"""
        if self.active_session_id:
            # Update and return the session in a single query
            session = await db.fetchrow('''
                UPDATE live_sessions
                SET status = 'completed', ended_at = NOW()
                WHERE session_id = $1
                RETURNING session_id, started_at, ended_at
            ''', self.active_session_id)

            logger.info(f"Ended session {self.active_session_id}")
            self.active_session_id = None
            self.gift_streaks.clear()

            return session

        return None

    @app_commands.command(name="tiktok-connect", description="Connect to a TikTok live stream")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def tiktok_connect(self, interaction: discord.Interaction, 
                            username: str, persistent: bool = True):
        if not interaction.response.is_done():
            await interaction.response.defer()

        if self.client:
            await interaction.followup.send("❌ Already connected to a TikTok stream. Disconnect first.")
            return

        self.username = username
        self.persistent_connection = persistent

        try:
            self.client = TikTokLiveClient(unique_id=username)

            @self.client.on(ConnectEvent)
            async def on_connect(event: ConnectEvent):
                logger.info(f"Connected to @{username}'s live stream")
                self.session_id = await db.fetchval(
                    'INSERT INTO live_sessions (tiktok_username, status) VALUES ($1, $2) RETURNING id',
                    username, 'active'
                )
                self.active_session_id = self.session_id
                
                # Update session_id column to match id
                await db.execute(
                    'UPDATE live_sessions SET session_id = id WHERE id = $1',
                    self.session_id
                )

            @self.client.on(DisconnectEvent)
            async def on_disconnect(event: DisconnectEvent):
                logger.info(f"Disconnected from @{username}'s stream")
                # Ensure session is ended on disconnect if it was active
                if self.active_session_id:
                    await self.end_active_session()

            @self.client.on(LiveEndEvent)
            async def on_live_end(event: LiveEndEvent):
                logger.info(f"@{username}'s live stream ended")
                await self.end_active_session() # Use the modified end_active_session
                await self.disconnect_tiktok()

            @self.client.on(GiftEvent)
            async def on_gift(event: GiftEvent):
                await self.process_gift(event)

            @self.client.on(JoinEvent)
            async def on_join(event: JoinEvent):
                handle_id = await self.get_or_create_tiktok_account(
                    event.user.unique_id,
                    getattr(event.user, 'level', 0)
                )
                await self.log_interaction(handle_id, 'join', user_level=getattr(event.user, 'level', 0))

            @self.client.on(LikeEvent)
            async def on_like(event: LikeEvent):
                handle_id = await self.get_or_create_tiktok_account(
                    event.user.unique_id,
                    getattr(event.user, 'level', 0)
                )
                like_count = getattr(event, 'count', getattr(event, 'total_likes', 1))
                await self.log_interaction(handle_id, 'like', str(like_count), user_level=getattr(event.user, 'level', 0))

            @self.client.on(CommentEvent)
            async def on_comment(event: CommentEvent):
                try:
                    handle_id = await self.get_or_create_tiktok_account(
                        event.user.unique_id,
                        getattr(event.user, 'level', 0)
                    )
                    await self.log_interaction(handle_id, 'comment', event.comment, user_level=getattr(event.user, 'level', 0))
                except Exception as e:
                    logger.error(f"Error processing comment: {e}")

            @self.client.on(ShareEvent)
            async def on_share(event: ShareEvent):
                handle_id = await self.get_or_create_tiktok_account(
                    event.user.unique_id,
                    getattr(event.user, 'level', 0)
                )
                await self.log_interaction(handle_id, 'share', user_level=getattr(event.user, 'level', 0))

            @self.client.on(FollowEvent)
            async def on_follow(event: FollowEvent):
                handle_id = await self.get_or_create_tiktok_account(
                    event.user.unique_id,
                    getattr(event.user, 'level', 0)
                )
                await self.log_interaction(handle_id, 'follow', user_level=getattr(event.user, 'level', 0))

            @self.client.on(RoomUserSeqEvent)
            async def on_viewer_count(event: RoomUserSeqEvent):
                if self.session_id:
                    viewer_count = getattr(event, 'viewerCount', 0)
                    await db.execute(
                        'INSERT INTO viewer_count_snapshots (session_id, viewer_count) VALUES ($1, $2)',
                        self.session_id, viewer_count
                    )

            asyncio.create_task(self.client.connect())
            await interaction.followup.send(f"✅ Connecting to @{username}'s stream...")

        except Exception as e:
            logger.error(f"Error connecting to TikTok: {e}")
            await interaction.followup.send(f"❌ Error: {str(e)}")

    async def disconnect_tiktok(self):
        if self.client:
            try:
                await self.client.disconnect()
            except:
                pass
            self.client = None

        # Ensure session is ended if it was active
        if self.active_session_id:
            await self.end_active_session()

        self.session_id = None
        self.active_session_id = None


    @app_commands.command(name="tiktok-disconnect", description="Disconnect from TikTok live stream")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def tiktok_disconnect(self, interaction: discord.Interaction):
        if not interaction.response.is_done():
            await interaction.response.defer()

        if not self.client:
            await interaction.followup.send("❌ Not connected to any stream.")
            return

        await self.disconnect_tiktok()
        await interaction.followup.send("✅ Disconnected from TikTok stream.")

    @app_commands.command(name="tiktok-status", description="Check TikTok connection status")
    async def tiktok_status(self, interaction: discord.Interaction):
        if self.client and self.client.connected:
            embed = discord.Embed(
                title="✅ TikTok Connected",
                color=discord.Color.green()
            )
            embed.add_field(name="Username", value=f"@{self.username}")
            embed.add_field(name="Session ID", value=str(self.session_id))
            embed.add_field(name="Persistent", value="Yes" if self.persistent_connection else "No")
        else:
            embed = discord.Embed(
                title="❌ TikTok Disconnected",
                color=discord.Color.red()
            )

        await interaction.response.send_message(embed=embed, ephemeral=True)

    def cog_unload(self):
        if self.client:
            asyncio.create_task(self.disconnect_tiktok())


async def setup(bot):
    await bot.add_cog(TikTokIntegration(bot))