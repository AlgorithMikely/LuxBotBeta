import discord
from discord.ext import commands
from discord import app_commands
import logging
from database import db

logger = logging.getLogger(__name__)


class Admin(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="set-submission-channel", description="Set the submissions channel")
    @app_commands.checks.has_permissions(administrator=True)
    async def set_submission_channel(self, interaction: discord.Interaction, 
                                    channel: discord.TextChannel):
        await interaction.response.defer()

        await db.execute('''
            INSERT INTO bot_config (key, channel_id)
            VALUES ('submission_channel', $1)
            ON CONFLICT (key) DO UPDATE
            SET channel_id = $1
        ''', channel.id)

        await interaction.followup.send(
            f"✅ Submissions channel set to {channel.mention}"
        )

        logger.info(f"Admin {interaction.user} set submission channel to {channel.id}")

    @app_commands.command(name="setup-live-queue", description="Setup live queue embed in a channel")
    @app_commands.checks.has_permissions(administrator=True)
    async def setup_live_queue(self, interaction: discord.Interaction, 
                              channel: discord.TextChannel):
        await interaction.response.defer()

        existing = await db.fetchrow(
            "SELECT * FROM persistent_embeds WHERE embed_type = 'live_queue' AND channel_id = $1",
            channel.id
        )

        if existing:
            await interaction.followup.send(
                f"❌ Live queue already exists in {channel.mention}"
            )
            return

        cog = self.bot.get_cog('PersistentEmbeds')
        embed = await cog.generate_live_queue_embed(0)
        message = await channel.send(embed=embed)

        await db.execute('''
            INSERT INTO persistent_embeds (embed_type, channel_id, message_id)
            VALUES ('live_queue', $1, $2)
        ''', channel.id, message.id)

        await interaction.followup.send(
            f"✅ Live queue embed created in {channel.mention}"
        )

    @app_commands.command(name="setup-reviewer-channel", description="Setup reviewer channel with embeds")
    @app_commands.checks.has_permissions(administrator=True)
    async def setup_reviewer_channel(self, interaction: discord.Interaction, 
                                     channel: discord.TextChannel):
        await interaction.response.defer()

        cog = self.bot.get_cog('PersistentEmbeds')

        main_embed = await cog.generate_reviewer_main_embed(0)
        from cogs.persistent_embeds import ReviewerView
        main_view = ReviewerView(self.bot, 'reviewer_main')
        main_message = await channel.send(embed=main_embed, view=main_view)

        await db.execute('''
            INSERT INTO persistent_embeds (embed_type, channel_id, message_id)
            VALUES ('reviewer_main', $1, $2)
            ON CONFLICT (embed_type, channel_id) DO UPDATE
            SET message_id = $2, is_active = TRUE
        ''', channel.id, main_message.id)

        pending_embed = await cog.generate_reviewer_pending_embed(0)
        pending_view = ReviewerView(self.bot, 'reviewer_pending')
        pending_message = await channel.send(embed=pending_embed, view=pending_view)

        await db.execute('''
            INSERT INTO persistent_embeds (embed_type, channel_id, message_id)
            VALUES ('reviewer_pending', $1, $2)
            ON CONFLICT (embed_type, channel_id) DO UPDATE
            SET message_id = $2, is_active = TRUE
        ''', channel.id, pending_message.id)

        await interaction.followup.send(
            f"✅ Reviewer channel setup complete in {channel.mention}"
        )

    @app_commands.command(name="set-metrics-channel", description="Set the metrics reporting channel")
    @app_commands.checks.has_permissions(administrator=True)
    async def set_metrics_channel(self, interaction: discord.Interaction, 
                                 channel: discord.TextChannel):
        await interaction.response.defer()

        await db.execute('''
            INSERT INTO bot_config (key, channel_id)
            VALUES ('metrics_channel', $1)
            ON CONFLICT (key) DO UPDATE
            SET channel_id = $1
        ''', channel.id)

        await interaction.followup.send(
            f"✅ Metrics channel set to {channel.mention}"
        )

    @app_commands.command(name="set-archive-channel", description="Set the file archive channel for submissions")
    @app_commands.checks.has_permissions(administrator=True)
    async def set_archive_channel(self, interaction: discord.Interaction, 
                                 channel: discord.TextChannel):
        await interaction.response.defer()

        await db.execute('''
            INSERT INTO bot_config (key, channel_id)
            VALUES ('archive_channel', $1)
            ON CONFLICT (key) DO UPDATE
            SET channel_id = $1
        ''', channel.id)

        await interaction.followup.send(
            f"✅ Archive channel set to {channel.mention}"
        )
        
        logger.info(f"Admin {interaction.user} set archive channel to {channel.id}")

    @app_commands.command(name="post-live-metrics", description="Post metrics for the last live session")
    @app_commands.checks.has_permissions(administrator=True)
    async def post_live_metrics(self, interaction: discord.Interaction):
        """Post metrics from the most recent completed live session"""

        if not interaction.response.is_done():
            await interaction.response.defer()

        tiktok_cog = self.bot.get_cog('TikTokIntegration')
        if not tiktok_cog:
            await interaction.followup.send("❌ TikTok integration not loaded")
            return

        # end_active_session now returns the session data directly
        session = await tiktok_cog.end_active_session()

        if not session:
            await interaction.followup.send("❌ No active session to end")
            return

        metrics_channel_id = await db.fetchval(
            "SELECT channel_id FROM bot_config WHERE key = 'metrics_channel'"
        )

        if not metrics_channel_id:
            await interaction.followup.send(
                "❌ Metrics channel not configured. Use `/set-metrics-channel` first."
            )
            return

        # The session data is now directly available from end_active_session,
        # so we don't need to re-query for it.
        # The original query was:
        # last_session = await db.fetchrow('''
        #     SELECT * FROM live_sessions
        #     WHERE status = 'completed'
        #     ORDER BY ended_at DESC
        #     LIMIT 1
        # ''')
        # if not last_session:
        #     await interaction.followup.send("❌ No completed live sessions found.")
        #     return
        
        # We use the session data returned by end_active_session directly.
        # This assumes end_active_session returns a dictionary-like object 
        # with keys like 'id', 'tiktok_username', 'start_time', 'end_time'.
        # If the structure is different, this part might need adjustment.
        last_session = session 

        total_interactions = await db.fetchval(
            'SELECT COUNT(*) FROM tiktok_interactions WHERE session_id = $1',
            last_session['id']
        )

        total_gifts = await db.fetchval(
            'SELECT COUNT(*) FROM tiktok_interactions WHERE session_id = $1 AND interaction_type = $2',
            last_session['id'], 'gift'
        )

        total_coins = await db.fetchval(
            'SELECT COALESCE(SUM(coin_value), 0) FROM tiktok_interactions WHERE session_id = $1 AND interaction_type = $2',
            last_session['id'], 'gift'
        )

        unique_viewers = await db.fetchval(
            'SELECT COUNT(DISTINCT tiktok_account_id) FROM tiktok_interactions WHERE session_id = $1',
            last_session['id']
        )

        avg_viewers = await db.fetchval(
            'SELECT AVG(viewer_count) FROM viewer_count_snapshots WHERE session_id = $1',
            last_session['id']
        )

        peak_viewers = await db.fetchval(
            'SELECT MAX(viewer_count) FROM viewer_count_snapshots WHERE session_id = $1',
            last_session['id']
        )

        songs_played = await db.fetchval(
            'SELECT COUNT(*) FROM submissions WHERE played_time >= $1 AND played_time <= $2',
            last_session['started_at'], last_session['ended_at']
        )

        embed = discord.Embed(
            title=f"📊 Live Session Metrics - @{last_session['tiktok_username']}",
            color=discord.Color.purple()
        )

        duration = last_session['ended_at'] - last_session['started_at']
        hours = int(duration.total_seconds() // 3600)
        minutes = int((duration.total_seconds() % 3600) // 60)

        embed.add_field(name="Duration", value=f"{hours}h {minutes}m", inline=True)
        embed.add_field(name="Songs Played", value=str(songs_played), inline=True)
        embed.add_field(name="Total Interactions", value=str(total_interactions), inline=True)
        embed.add_field(name="Total Gifts", value=str(total_gifts), inline=True)
        embed.add_field(name="Total Coins", value=f"{total_coins:,}", inline=True)
        embed.add_field(name="Unique Viewers", value=str(unique_viewers), inline=True)

        if avg_viewers:
            embed.add_field(name="Avg Viewers", value=f"{int(avg_viewers)}", inline=True)
        if peak_viewers:
            embed.add_field(name="Peak Viewers", value=str(peak_viewers), inline=True)

        embed.set_footer(text=f"Session: {last_session['started_at'].strftime('%Y-%m-%d %H:%M')} - {last_session['ended_at'].strftime('%H:%M')}")

        metrics_channel = self.bot.get_channel(metrics_channel_id)
        if metrics_channel:
            await metrics_channel.send(embed=embed)
            await interaction.followup.send("✅ Metrics posted successfully!")
        else:
            await interaction.followup.send("❌ Metrics channel not found.")


async def setup(bot):
    await bot.add_cog(Admin(bot))