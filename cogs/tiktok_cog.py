import discord
import logging
import asyncio
import time
from discord.ext import commands, tasks
from discord import app_commands
from typing import Optional, Dict
from TikTokLive import TikTokLiveClient
from TikTokLive.events import CommentEvent, ConnectEvent, DisconnectEvent, GiftEvent, LikeEvent, ShareEvent, FollowEvent
from TikTokLive.client.errors import UserNotFoundError, UserOfflineError
from database import QueueLine

# --- Constants ---
# Re-implementing the tiered gift logic as requested
GIFT_TIER_MAP = {
    5000: QueueLine.TWENTYFIVEPLUSSKIP.value,
    2000: QueueLine.TENSKIP.value,
    1000: QueueLine.FIVESKIP.value,
}

INTERACTION_POINTS = {
    "like": 1,
    "comment": 2,
    "share": 5,
    "follow": 10,
}

@app_commands.default_permissions(administrator=True)
class TikTokCog(commands.GroupCog, name="tiktok", description="Commands for managing TikTok Live integration."):
    """Handles TikTok Live integration, interaction logging, and engagement rewards."""

    def __init__(self, bot: commands.Bot):
        self.bot: commands.Bot = bot
        logging.info("--- TikTokCog IS BEING INITIALIZED ---")
        self.bot.tiktok_client: Optional[TikTokLiveClient] = None
        self._is_connected = asyncio.Event()
        self._connection_task: Optional[asyncio.Task] = None
        self._connect_interaction: Optional[discord.Interaction] = None
        self.current_session_id: Optional[int] = None
        self.live_host_username: Optional[str] = None
        self._retry_enabled: bool = False
        self._retry_count: int = 0
        self._connection_start_time: Optional[float] = None
        self.score_sync_task.start()
        super().__init__()

    # FIXED BY JULES
    def cog_unload(self):
        """Clean up resources when the cog is unloaded."""
        self.score_sync_task.cancel()
        if self._connection_task and not self._connection_task.done():
            self._connection_task.cancel()

        # If connected, trigger the disconnection. The on_disconnect event will handle the cleanup.
        if self.is_connected and self.bot.tiktok_client:
            asyncio.create_task(self.bot.tiktok_client.disconnect())

    @property
    def is_connected(self) -> bool:
        return self._is_connected.is_set()

    # ... (rest of the connection and status logic remains the same) ...
    def _create_status_embed(self, title: str, description: str, color: discord.Color) -> discord.Embed:
        """Helper function to create a standardized status embed."""
        embed = discord.Embed(title=title, description=description, color=color)
        embed.set_footer(text="TikTok Live Integration | Luxurious Radio")
        embed.timestamp = discord.utils.utcnow()
        return embed

    @app_commands.command(name="connect", description="Connect to a TikTok LIVE stream.")
    @app_commands.describe(
        unique_id="The @unique_id of the TikTok user to connect to.",
        persistent="Keep retrying until the user goes live (default: True)"
    )
    async def connect(self, interaction: discord.Interaction, unique_id: str, persistent: bool = True):
        """Connects the bot to a specified TikTok Live stream with optional persistent retry."""
        if self.is_connected:
            await interaction.response.send_message("Already connected to a TikTok LIVE. Please disconnect first.", ephemeral=True)
            return

        if self._connection_task and not self._connection_task.done():
            await interaction.response.send_message("A connection attempt is already in progress. Use `/tiktok status` to check progress or `/tiktok disconnect` to cancel.", ephemeral=True)
            return

        self._retry_enabled = persistent
        self._retry_count = 0
        self._connection_start_time = time.time()
        
        embed = self._create_status_embed("⏳ Connecting...", "Status: Initializing connection...", discord.Color.light_grey())
        await interaction.response.send_message(embed=embed, ephemeral=True)
        self._connection_task = asyncio.create_task(self._background_connect(interaction, unique_id))

    async def _background_connect(self, interaction: discord.Interaction, unique_id: str):
        """Asynchronous method to handle the TikTok connection with retry logic."""
        async def edit_status(title, description, color):
            try:
                await interaction.edit_original_response(embed=self._create_status_embed(title, description, color))
            except discord.NotFound:
                logging.warning("Connection status message was deleted")

        clean_unique_id = unique_id.strip().lstrip('@')
        self.live_host_username = clean_unique_id
        
        while True:
            try:
                self._retry_count += 1
                elapsed = int(time.time() - self._connection_start_time) if self._connection_start_time else 0
                
                if self._retry_count == 1:
                    await edit_status("⏳ Connecting...", "Status: Creating TikTok Client...", discord.Color.blue())
                else:
                    retry_msg = f"Status: Retry attempt #{self._retry_count} (elapsed: {elapsed}s)\nWaiting for `@{clean_unique_id}` to go live..."
                    await edit_status("🔄 Retrying Connection...", retry_msg, discord.Color.orange())

                client = TikTokLiveClient(unique_id=f"@{clean_unique_id}")
                self.bot.tiktok_client = client

                # Add all event listeners
                client.add_listener(ConnectEvent, self.on_connect)
                client.add_listener(DisconnectEvent, self.on_disconnect)
                client.add_listener(LikeEvent, self.on_like)
                client.add_listener(CommentEvent, self.on_comment)
                client.add_listener(ShareEvent, self.on_share)
                client.add_listener(GiftEvent, self.on_gift)
                client.add_listener(FollowEvent, self.on_follow)
                self._connect_interaction = interaction

                await edit_status("⏳ Connecting...", f"Status: Attempting connection to `@{clean_unique_id}`...", discord.Color.blue())
                await client.start()
                
                # If we get here, connection succeeded
                break

            except UserNotFoundError:
                await edit_status("❌ Connection Failed", f"**Reason:** TikTok user `@{unique_id}` was not found.\n\nThis username doesn't exist on TikTok.", discord.Color.red())
                self._reset_state()
                break
                
            except UserOfflineError:
                if not self._retry_enabled:
                    await edit_status("❌ Connection Failed", f"**Reason:** User `@{unique_id}` is not currently LIVE.\n\nEnable persistent mode to keep retrying.", discord.Color.red())
                    self._reset_state()
                    break
                
                # Retry logic for offline user
                if self._retry_count >= 3:
                    # After 3 attempts, update status less frequently
                    await asyncio.sleep(30)
                else:
                    await asyncio.sleep(10)
                continue
                
            except asyncio.CancelledError:
                await edit_status("🛑 Connection Cancelled", "The connection attempt was manually cancelled.", discord.Color.red())
                self._reset_state()
                raise
                
            except Exception as e:
                logging.error(f"Failed to connect to TikTok in background: {e}", exc_info=True)
                
                if self._retry_enabled and self._retry_count < 5:
                    await asyncio.sleep(15)
                    continue
                else:
                    await edit_status("❌ Connection Failed", f"**Reason:** An unexpected error occurred.\n```\n{str(e)[:200]}\n```", discord.Color.red())
                    self._reset_state()
                    break
            
            finally:
                # Cleanup if we're not connected and not retrying
                if not self.is_connected and not self._retry_enabled:
                    self._reset_state()

    @app_commands.command(name="status", description="Check the current TikTok connection status.")
    async def status(self, interaction: discord.Interaction):
        """Display the current TikTok connection status with detailed information."""
        if self.is_connected and self.bot.tiktok_client:
            elapsed = int(time.time() - self._connection_start_time) if self._connection_start_time else 0
            hours, remainder = divmod(elapsed, 3600)
            minutes, seconds = divmod(remainder, 60)
            uptime_str = f"{hours}h {minutes}m {seconds}s" if hours > 0 else f"{minutes}m {seconds}s"
            
            embed = discord.Embed(
                title="✅ TikTok Connection Active",
                description=f"Connected to **@{self.live_host_username}**",
                color=discord.Color.green()
            )
            embed.add_field(name="Room ID", value=f"`{self.bot.tiktok_client.room_id}`", inline=True)
            embed.add_field(name="Session ID", value=f"`{self.current_session_id or 'N/A'}`", inline=True)
            embed.add_field(name="Connection Uptime", value=uptime_str, inline=True)
            embed.set_footer(text="Use /tiktok disconnect to end the session")
        elif self._connection_task and not self._connection_task.done():
            elapsed = int(time.time() - self._connection_start_time) if self._connection_start_time else 0
            status_text = f"Attempting to connect to **@{self.live_host_username or 'Unknown'}**"
            
            embed = discord.Embed(
                title="🔄 Connection In Progress",
                description=status_text,
                color=discord.Color.orange()
            )
            embed.add_field(name="Retry Count", value=f"`{self._retry_count}`", inline=True)
            embed.add_field(name="Persistent Mode", value="✅ Enabled" if self._retry_enabled else "❌ Disabled", inline=True)
            embed.add_field(name="Elapsed Time", value=f"`{elapsed}s`", inline=True)
            embed.set_footer(text="Use /tiktok disconnect to cancel the connection attempt")
        else:
            embed = discord.Embed(
                title="❌ Not Connected",
                description="The bot is not currently connected to any TikTok LIVE stream.",
                color=discord.Color.red()
            )
            embed.set_footer(text="Use /tiktok connect to start a connection")
        
        embed.timestamp = discord.utils.utcnow()
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="disconnect", description="Disconnect from the TikTok LIVE stream.")
    async def disconnect(self, interaction: discord.Interaction):
        """Signals the TikTok client to disconnect or cancel connection attempt."""
        # Check if there's an active connection
        if self.is_connected and self.bot.tiktok_client:
            await interaction.response.send_message("🔌 Disconnecting from TikTok LIVE... Session summary will be posted shortly.", ephemeral=True)
            await self.bot.tiktok_client.disconnect()
            return
        
        # Check if there's a connection attempt in progress
        if self._connection_task and not self._connection_task.done():
            self._connection_task.cancel()
            await interaction.response.send_message("🛑 Connection attempt cancelled successfully.", ephemeral=True)
            return
        
        # Not connected or attempting to connect
        await interaction.response.send_message("Not currently connected or attempting to connect to any stream.", ephemeral=True)

    def _reset_state(self):
        """Resets all internal state variables for the connection."""
        if self._connection_task and not self._connection_task.done():
            self._connection_task.cancel()

        self.bot.tiktok_client = None
        self._is_connected.clear()
        self.current_session_id = None
        self.live_host_username = None
        self._connect_interaction = None
        self._retry_enabled = False
        self._retry_count = 0
        self._connection_start_time = None
        logging.info("TIKTOK: Internal connection state has been reset.")

    async def _cleanup_connection(self):
        """Handles cleanup when disconnecting from TikTok LIVE."""
        if self.current_session_id:
            await self.bot.db.end_live_session(self.current_session_id)
            summary = await self.bot.db.get_live_session_summary(self.current_session_id)
            await self._post_live_summary(summary)
        self._reset_state()

    async def _post_live_summary(self, summary: Dict[str, int]):
        """Posts the live session summary to the admin/debug channel."""
        debug_channel_id = self.bot.settings_cache.get('debug_channel_id')
        if not debug_channel_id: return
        channel = self.bot.get_channel(int(debug_channel_id))
        if not channel: return

        # --- Overall Summary (Existing) ---
        overall_embed = discord.Embed(
            title=f"📈 Overall Live Summary for {self.live_host_username}",
            description="Summary of all interactions during the last session.",
            color=discord.Color.blurple()
        )
        overall_embed.add_field(name="Likes", value=f"{summary.get('like', 0):,}", inline=True)
        overall_embed.add_field(name="Comments", value=f"{summary.get('comment', 0):,}", inline=True)
        overall_embed.add_field(name="Shares", value=f"{summary.get('share', 0):,}", inline=True)
        overall_embed.add_field(name="Follows", value=f"{summary.get('follow', 0):,}", inline=True)
        overall_embed.add_field(name="Gifts Received", value=f"{summary.get('gift', 0):,}", inline=True)
        overall_embed.add_field(name="Total Coins", value=f"{summary.get('gift_coins', 0):,}", inline=True)
        overall_embed.set_footer(text=f"Session ID: {self.current_session_id}")
        overall_embed.timestamp = discord.utils.utcnow()

        try:
            await channel.send(embed=overall_embed)
        except discord.Forbidden:
            logging.error(f"Missing permissions to send summary to channel {debug_channel_id}")
            return # Can't send anything if we don't have perms

        # --- Per-User Summary (New) ---
        user_stats = await self.bot.db.get_session_user_stats(self.current_session_id)
        submission_counts = await self.bot.db.get_session_submission_counts(self.current_session_id)

        if not user_stats:
            return # No users to report on

        user_embed = discord.Embed(
            title=f"👥 Per-User Stats for {self.live_host_username}",
            description="Top contributors for the last session.",
            color=discord.Color.dark_green()
        )
        user_embed.set_footer(text=f"Session ID: {self.current_session_id}")
        user_embed.timestamp = discord.utils.utcnow()

        description_lines = []
        for i, user_data in enumerate(user_stats[:10]): # Top 10 contributors
            discord_id = user_data['linked_discord_id']
            user = self.bot.get_user(discord_id) or f"ID: {discord_id}"
            subs = submission_counts.get(discord_id, 0)

            stats_line = (
                f"**{i+1}. {user}** (`{user_data['tiktok_username']}`)\n"
                f"> Subs: `{subs}` | Likes: `{user_data['likes']}` | Comments: `{user_data['comments']}` | "
                f"Shares: `{user_data['shares']}` | Coins: `{int(user_data['gift_coins'])}`\n"
            )
            description_lines.append(stats_line)

        user_embed.description = "\n".join(description_lines)
        if len(user_stats) > 10:
            user_embed.description += f"\n...and {len(user_stats) - 10} more contributors."

        try:
            await channel.send(embed=user_embed)
        except discord.Forbidden:
            logging.error(f"Missing permissions to send per-user summary to channel {debug_channel_id}")

    # --- Event Handlers ---
    async def on_connect(self, _: ConnectEvent):
        """Handles the connection event, starting a new live session."""
        self._is_connected.set()
        logging.info(f"TIKTOK: Connected to room ID {self.bot.tiktok_client.room_id}")

        if self.live_host_username:
            self.current_session_id = await self.bot.db.start_live_session(self.live_host_username)
            logging.info(f"TIKTOK: Started live session with ID {self.current_session_id}")

        if self._connect_interaction:
            await self._connect_interaction.edit_original_response(
                embed=self._create_status_embed("✅ Connected!", f"Successfully connected to **{self.bot.tiktok_client.unique_id}**'s LIVE stream.", discord.Color.green())
            )

    async def on_disconnect(self, _: DisconnectEvent):
        logging.info("TIKTOK: Disconnected from stream. Cleaning up...")
        await self._cleanup_connection()

    async def _handle_interaction(self, event, interaction_type: str, points: int, value: Optional[str] = None, coin_value: Optional[int] = None):
        """Generic interaction logger and point awarder."""
        if not self.current_session_id or not hasattr(event, 'user') or not hasattr(event.user, 'unique_id'):
            return

        try:
            tiktok_account_id = await self.bot.db.upsert_tiktok_account(event.user.unique_id)
            await self.bot.db.log_tiktok_interaction(self.current_session_id, tiktok_account_id, interaction_type, value, coin_value)

            # Add points to TikTok handle directly (regardless of Discord link)
            await self.bot.db.add_points_to_tiktok_handle(event.user.unique_id, points)
            
            # Also add points to linked Discord user if exists
            discord_id = await self.bot.db.get_discord_id_from_handle(event.user.unique_id)
            if discord_id:
                await self.bot.db.add_points_to_user(discord_id, points)
        except Exception as e:
            logging.error(f"Failed to handle TikTok interaction ({interaction_type}): {e}", exc_info=True)

    async def on_like(self, event: LikeEvent):
        await self._handle_interaction(event, 'like', INTERACTION_POINTS['like'])

    async def on_comment(self, event: CommentEvent):
        await self._handle_interaction(event, 'comment', INTERACTION_POINTS['comment'], value=event.comment)

    async def on_share(self, event: ShareEvent):
        await self._handle_interaction(event, 'share', INTERACTION_POINTS['share'])

    async def on_follow(self, event: FollowEvent):
        await self._handle_interaction(event, 'follow', INTERACTION_POINTS['follow'])

    async def on_gift(self, event: GiftEvent):
        if event.gift.streakable and event.streaking: return

        # Award points for all gifts
        # Updated point logic: 2 points per coin for gifts under 1000, otherwise 1 point per coin
        if event.gift.diamond_count < 1000:
            points = event.gift.diamond_count * 2
        else:
            points = event.gift.diamond_count

        await self._handle_interaction(event, 'gift', points, value=event.gift.name, coin_value=event.gift.diamond_count)

        # Tiered skip logic
        target_line_name: Optional[str] = None
        for coins, line_name in sorted(GIFT_TIER_MAP.items(), key=lambda item: item[0], reverse=True):
            if event.gift.diamond_count >= coins:
                target_line_name = line_name
                break

        if target_line_name:
            try:
                discord_id = await self.bot.db.get_discord_id_from_handle(event.user.unique_id)
                if not discord_id: return

                submission = await self.bot.db.find_gift_rewardable_submission(discord_id)
                if not submission: return

                original_line = await self.bot.db.move_submission(submission['public_id'], target_line_name)
                if original_line and original_line != target_line_name:
                    await self.bot.dispatch_queue_update() # FIXED BY JULES
                    logging.info(f"TIKTOK: Rewarded user {discord_id} with move to {target_line_name} for a {event.gift.diamond_count}-coin gift.")
                    user = self.bot.get_user(discord_id)
                    if user:
                        try:
                            await user.send(f"🎉 Thank you for the {event.gift.diamond_count}-coin gift! Your submission **{submission['artist_name']} - {submission['song_name']}** has been moved to the **{target_line_name}** queue as a reward.")
                        except discord.Forbidden:
                            pass # Can't send DMs, oh well
            except Exception as e:
                logging.error(f"Error processing tiered gift reward: {e}", exc_info=True)

    # --- Background Tasks ---
    # FIXED BY Replit: Points tracking with periodic sync - verified working
    @tasks.loop(seconds=15)
    async def score_sync_task(self):
        """Periodically syncs the user points with the submission scores in the free queue."""
        try:
            await self.bot.db.sync_submission_scores()
        except Exception as e:
            logging.error(f"Error in score_sync_task: {e}", exc_info=True)

    @score_sync_task.before_loop
    async def before_score_sync_task(self):
        await self.bot.wait_until_ready()

async def setup(bot):
    await bot.add_cog(TikTokCog(bot))