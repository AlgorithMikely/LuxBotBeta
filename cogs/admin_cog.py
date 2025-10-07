"""
Admin Cog - Handles administrative commands for queue management
"""

import discord
from discord.ext import commands
from discord import app_commands
from database import QueueLine
from typing import Optional
from .checks import is_admin
import random
import string

class NextActionView(discord.ui.View):
    def __init__(self, bot, submission_public_id: str):
        super().__init__(timeout=3600)  # 1 hour timeout
        self.bot = bot
        self.submission_public_id = submission_public_id

    @discord.ui.button(label="Bookmark", style=discord.ButtonStyle.success, emoji="🔖")
    async def bookmark_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            await interaction.response.defer(ephemeral=True)

            bookmark_channel_id = self.bot.settings_cache.get('bookmark_channel_id')
            if not bookmark_channel_id:
                await interaction.followup.send("❌ No bookmark channel has been set. Use `/setbookmarkchannel` first.", ephemeral=True)
                return

            bookmark_channel = self.bot.get_channel(bookmark_channel_id)
            if not bookmark_channel:
                await interaction.followup.send("❌ Bookmark channel not found. Please set a new one.", ephemeral=True)
                return

            submission = await self.bot.db.get_submission_by_id(self.submission_public_id)
            if not submission:
                await interaction.followup.send(f"❌ Submission #{self.submission_public_id} not found.", ephemeral=True)
                return

            embed = discord.Embed(
                title="🔖 Bookmarked Submission",
                description=f"Bookmarked by {interaction.user.mention}",
                color=discord.Color.gold()
            )

            embed.add_field(name="Submission ID", value=f"#{submission['public_id']}", inline=True)
            embed.add_field(name="Queue Line", value=submission['queue_line'], inline=True)
            embed.add_field(name="Submitted By", value=submission['username'], inline=True)
            embed.add_field(name="Artist", value=submission['artist_name'], inline=True)
            embed.add_field(name="Song", value=submission['song_name'], inline=True)
            embed.add_field(name="User ID", value=submission['user_id'], inline=True)

            if submission['link_or_file'].startswith('http'):
                embed.add_field(name="Link", value=f"[Click Here]({submission['link_or_file']})", inline=False)
            else:
                embed.add_field(name="File", value=submission['link_or_file'], inline=False)

            if submission.get('tiktok_username'):
                embed.add_field(name="TikTok", value=submission['tiktok_username'], inline=True)

            if submission.get('note'):
                embed.add_field(name="Note", value=submission['note'], inline=False)

            embed.set_footer(text=f"Originally submitted on {submission['submission_time']} | Luxurious Radio By Emerald Beats")
            embed.timestamp = discord.utils.utcnow()

            await bookmark_channel.send(embed=embed)

            button.disabled = True
            button.label = "Bookmarked"
            await interaction.edit_original_response(view=self)

        except Exception as e:
            error_message = f"❌ Error bookmarking submission: {str(e)}"
            if interaction.response.is_done():
                await interaction.followup.send(error_message, ephemeral=True)
            else:
                await interaction.response.send_message(error_message, ephemeral=True)

class AdminCog(commands.Cog):
    """Cog for administrative queue management"""
    
    def __init__(self, bot):
        self.bot = bot
    
    async def _update_queues(self, *queue_lines):
        """Helper to update queue displays for specified lines."""
        if hasattr(self.bot, 'get_cog') and self.bot.get_cog('QueueCog'):
            queue_cog = self.bot.get_cog('QueueCog')
            for line in queue_lines:
                if line:
                    await queue_cog.update_queue_display(line)

    @app_commands.command(name="setplaying", description="[ADMIN] Set the currently playing submission for interaction tracking.")
    @app_commands.describe(submission_id="The ID of the submission to set as active (e.g., #123456)")
    @is_admin()
    async def set_playing(self, interaction: discord.Interaction, submission_id: str):
        """Manually sets the submission that is considered 'now playing' for TikTok scoring."""
        await interaction.response.defer(ephemeral=True)
        public_id = submission_id.strip('#')

        submission = await self.bot.db.get_submission_by_id(public_id)
        if not submission:
            await interaction.followup.send(f"❌ Submission `#{public_id}` not found.", ephemeral=True)
            return

        self.bot.currently_playing_submission_id = public_id

        embed = discord.Embed(
            title="🎯 Active Submission Set",
            description=f"Submission `#{public_id}` (**{submission['artist_name']} - {submission['song_name']}**) is now the active track for interaction scoring.",
            color=discord.Color.green()
        )
        await interaction.followup.send(embed=embed, ephemeral=True)

    @app_commands.command(name="setline", description="Set the channel for a queue line")
    @app_commands.describe(
        line="The queue line to configure",
        channel="The text channel to use for this line"
    )
    @app_commands.choices(line=[
        app_commands.Choice(name=ql.value, value=ql.value) for ql in QueueLine
    ])
    @is_admin()
    async def set_line(self, interaction: discord.Interaction, line: str, channel: discord.TextChannel):
        """Set the channel for a queue line with detailed feedback."""
        await interaction.response.defer(ephemeral=True, thinking=True)

        try:
            # Step 1: Call the database function
            await interaction.followup.send(f"⚙️ Accessing the database to set **{line}**...", ephemeral=True)
            await self.bot.db.set_channel_for_line(line, channel.id)

            # Step 2: Update the queue display
            await interaction.followup.send("🔄 Updating the queue display...", ephemeral=True)
            await self._update_queues(line)
            
            # Step 3: Final confirmation
            embed = discord.Embed(
                title="✅ Line Channel Set Successfully",
                description=f"The **{line}** line has been set to {channel.mention}.",
                color=discord.Color.green()
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
            
        except Exception as e:
            # Send a detailed error message if anything fails
            error_embed = discord.Embed(
                title=f"❌ An Error Occurred While Setting '{line}'",
                description="Failed to set the line channel. Here's the error information:",
                color=discord.Color.red()
            )
            error_embed.add_field(name="Error Details", value=f"```\n{e}\n```", inline=False)
            await interaction.followup.send(embed=error_embed, ephemeral=True)
    
    @app_commands.command(name="move", description="Move a submission to a different queue line")
    @app_commands.describe(
        submission_id="The ID of the submission to move (e.g., #123456)",
        target_line="The target queue line"
    )
    @app_commands.choices(target_line=[
        app_commands.Choice(name=ql.value, value=ql.value) for ql in QueueLine if ql != QueueLine.CALLS_PLAYED
    ])
    @is_admin()
    async def move_submission(self, interaction: discord.Interaction, submission_id: str, target_line: str):
        """Move a submission between queue lines"""
        public_id = submission_id.strip('#')
        try:
            original_line = await self.bot.db.move_submission(public_id, target_line)
            
            if original_line:
                await self._update_queues(original_line, target_line)
                
                embed = discord.Embed(
                    title="✅ Submission Moved",
                    description=f"Submission `#{public_id}` has been moved to **{target_line}** line.",
                    color=discord.Color.green()
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
            else:
                await interaction.response.send_message(
                    f"❌ Submission `#{public_id}` not found.",
                    ephemeral=True
                )
                
        except Exception as e:
            await interaction.response.send_message(
                f"❌ Error moving submission: {str(e)}", 
                ephemeral=True
            )
    
    @app_commands.command(name="remove", description="Remove a submission from the queue")
    @app_commands.describe(submission_id="The ID of the submission to remove (e.g., #123456)")
    @is_admin()
    async def remove_submission(self, interaction: discord.Interaction, submission_id: str):
        """Remove a submission from the queue"""
        public_id = submission_id.strip('#')
        try:
            original_line = await self.bot.db.remove_submission(public_id)
            
            if original_line:
                await self._update_queues(original_line)
                
                embed = discord.Embed(
                    title="✅ Submission Removed",
                    description=f"Submission `#{public_id}` has been removed from the queue.",
                    color=discord.Color.green()
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
            else:
                await interaction.response.send_message(
                    f"❌ Submission `#{public_id}` not found.",
                    ephemeral=True
                )
                
        except Exception as e:
            await interaction.response.send_message(
                f"❌ Error removing submission: {str(e)}", 
                ephemeral=True
            )
    
    @app_commands.command(name="setsubmissionchannel", description="Set the channel for submissions (auto-moderated)")
    @app_commands.describe(channel="The text channel to use for submissions")
    @is_admin()
    async def set_submission_channel(self, interaction: discord.Interaction, channel: discord.TextChannel):
        """Set the channel for submissions"""
        try:
            await self.bot.db.set_submission_channel(channel.id)
            
            embed = discord.Embed(
                title="✅ Submission Channel Set",
                description=f"Submissions channel is now set to {channel.mention}\n\n"
                           f"Non-admin messages will be automatically removed and users will be guided to use `/submit` or `/submitfile` commands.",
                color=discord.Color.green()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            
        except Exception as e:
            await interaction.response.send_message(
                f"❌ Error setting submission channel: {str(e)}", 
                ephemeral=True
            )
    
    @app_commands.command(name="next", description="Get the next submission to review")
    @is_admin()
    async def next_submission(self, interaction: discord.Interaction):
        """Get the next submission following priority order"""
        try:
            # When /next is called, the new submission becomes the one tracking points.
            next_sub = await self.bot.db.take_next_to_calls_played()

            if not next_sub:
                self.bot.currently_playing_submission_id = None
                embed = discord.Embed(
                    title="📭 Queue Empty",
                    description="No submissions are currently in the queue. Interaction tracking is now paused.",
                    color=discord.Color.blue()
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return

            # Set the new submission as the one to track for interactions.
            self.bot.currently_playing_submission_id = next_sub['public_id']
            
            # Announce to #now-playing channel if set
            now_playing_channel_id = self.bot.settings_cache.get('now_playing_channel_id')
            if now_playing_channel_id:
                channel = self.bot.get_channel(now_playing_channel_id)
                if channel:
                    user = self.bot.get_user(next_sub['user_id'])
                    mention = user.mention if user else f"<@{next_sub['user_id']}>"
                    announcement = f"🎶 Now Playing: {next_sub['artist_name']} – {next_sub['song_name']} (submitted by {mention})"
                    await channel.send(announcement)

            embed = discord.Embed(
                title="🎵 Now Playing - Moved to Calls Played",
                description=f"Moved from **{next_sub['original_line']}** line to **Calls Played**",
                color=discord.Color.gold()
            )
            
            embed.add_field(name="Submission ID", value=f"#{next_sub['public_id']}", inline=True)
            embed.add_field(name="Original Line", value=next_sub['original_line'], inline=True)
            embed.add_field(name="Submitted By", value=next_sub['username'], inline=True)
            embed.add_field(name="Artist", value=next_sub['artist_name'], inline=True)
            embed.add_field(name="Song", value=next_sub['song_name'], inline=True)
            
            if next_sub['link_or_file'].startswith('http'):
                embed.add_field(name="Link", value=f"[Click Here]({next_sub['link_or_file']})", inline=False)
            else:
                embed.add_field(name="File", value=next_sub['link_or_file'], inline=False)

            if next_sub.get('tiktok_username'):
                embed.add_field(name="TikTok", value=next_sub['tiktok_username'], inline=True)

            if next_sub.get('note'):
                embed.add_field(name="Note", value=next_sub['note'], inline=False)
            
            embed.add_field(
                name="🔴 Live Interaction Tracking",
                value=f"Submission `#{next_sub['public_id']}` is now **active** and accumulating interaction points.",
                inline=False
            )

            embed.set_footer(text=f"Submitted on {next_sub['submission_time']} | Luxurious Radio By Emerald Beats")
            
            view = NextActionView(self.bot, next_sub['public_id'])
            await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
            
            await self._update_queues(next_sub['original_line'], QueueLine.CALLS_PLAYED.value)
            
        except Exception as e:
            await interaction.response.send_message(
                f"❌ Error getting next submission: {str(e)}", 
                ephemeral=True
            )
    
    @app_commands.command(name="opensubmissions", description="Open submissions for the Free line")
    @is_admin()
    async def open_submissions(self, interaction: discord.Interaction):
        """Open submissions for the Free line"""
        try:
            await self.bot.db.set_free_line_status(True)
            embed = discord.Embed(
                title="✅ Free Line Opened",
                description="Users can now submit music to the **Free** line.",
                color=discord.Color.green()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ Error opening Free line: {str(e)}", ephemeral=True)
    
    @app_commands.command(name="closesubmissions", description="Close submissions for the Free line")
    @is_admin()
    async def close_submissions(self, interaction: discord.Interaction):
        """Close submissions for the Free line"""
        try:
            await self.bot.db.set_free_line_status(False)
            embed = discord.Embed(
                title="🚫 Free Line Closed",
                description="Users can no longer submit to the **Free** line. Skip submissions are still allowed.",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ Error closing Free line: {str(e)}", ephemeral=True)
    
    @app_commands.command(name="clearfree", description="Clear all submissions from the Free line")
    @is_admin()
    async def clear_free_line(self, interaction: discord.Interaction):
        """Clear all submissions from the Free line"""
        try:
            cleared_count = await self.bot.db.clear_free_line()
            await self._update_queues(QueueLine.FREE.value)
            
            embed = discord.Embed(
                title="🗑️ Free Line Cleared",
                description=f"Removed {cleared_count} submission{'s' if cleared_count != 1 else ''} from the Free line.",
                color=discord.Color.orange()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            
        except Exception as e:
            await interaction.response.send_message(f"❌ Error clearing Free line: {str(e)}", ephemeral=True)
    
    @app_commands.command(name="setbookmarkchannel", description="Set the channel for bookmarked submissions")
    @app_commands.describe(channel="The text channel to use for bookmarks")
    @is_admin()
    async def set_bookmark_channel(self, interaction: discord.Interaction, channel: discord.TextChannel):
        """Set the channel for bookmarked submissions with detailed feedback."""
        await interaction.response.defer(ephemeral=True, thinking=True)

        try:
            # Step 1: Call the database function
            await interaction.followup.send("⚙️ Accessing the database...", ephemeral=True)
            await self.bot.db.set_bookmark_channel(channel.id)

            # Step 2: Update the local cache
            await interaction.followup.send("📝 Updating live settings cache...", ephemeral=True)
            self.bot.settings_cache['bookmark_channel_id'] = channel.id

            # Step 3: Final confirmation
            embed = discord.Embed(
                title="✅ Bookmark Channel Set Successfully",
                description=f"The bookmark channel has been set to {channel.mention}.",
                color=discord.Color.green()
            )
            await interaction.followup.send(embed=embed, ephemeral=True)

        except Exception as e:
            # Send a detailed error message if anything fails
            error_embed = discord.Embed(
                title="❌ An Error Occurred",
                description="Failed to set the bookmark channel. Here's the error information:",
                color=discord.Color.red()
            )
            error_embed.add_field(name="Error Details", value=f"```\n{e}\n```", inline=False)
            await interaction.followup.send(embed=error_embed, ephemeral=True)

    @app_commands.command(name="setnowplayingchannel", description="Set the channel for 'Now Playing' announcements")
    @app_commands.describe(channel="The text channel to use for announcements")
    @is_admin()
    async def set_now_playing_channel(self, interaction: discord.Interaction, channel: discord.TextChannel):
        """Set the channel for 'Now Playing' announcements"""
        try:
            await self.bot.db.set_now_playing_channel(channel.id)
            self.bot.settings_cache['now_playing_channel_id'] = channel.id
            embed = discord.Embed(
                title="✅ 'Now Playing' Channel Set",
                description=f"'Now Playing' announcements will be sent to {channel.mention}",
                color=discord.Color.green()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ Error setting 'Now Playing' channel: {str(e)}", ephemeral=True)
    
    @app_commands.command(name="bookmark", description="Bookmark a submission to the bookmark channel")
    @app_commands.describe(submission_id="The ID of the submission to bookmark (e.g., #123456)")
    @is_admin()
    async def bookmark_submission(self, interaction: discord.Interaction, submission_id: str):
        """Bookmark a submission to the designated bookmark channel"""
        public_id = submission_id.strip('#')
        try:
            bookmark_channel_id = self.bot.settings_cache.get('bookmark_channel_id')
            if not bookmark_channel_id:
                await interaction.response.send_message("❌ No bookmark channel has been set. Use `/setbookmarkchannel` first.", ephemeral=True)
                return
            
            bookmark_channel = self.bot.get_channel(bookmark_channel_id)
            if not bookmark_channel:
                await interaction.response.send_message("❌ Bookmark channel not found. Please set a new one.", ephemeral=True)
                return
            
            submission = await self.bot.db.get_submission_by_id(public_id)
            if not submission:
                await interaction.response.send_message(f"❌ Submission `#{public_id}` not found.", ephemeral=True)
                return
            
            embed = discord.Embed(
                title="🔖 Bookmarked Submission",
                description=f"Bookmarked by {interaction.user.mention}",
                color=discord.Color.gold()
            )
            
            embed.add_field(name="Submission ID", value=f"#{submission['public_id']}", inline=True)
            embed.add_field(name="Queue Line", value=submission['queue_line'], inline=True)
            embed.add_field(name="Submitted By", value=submission['username'], inline=True)
            embed.add_field(name="Artist", value=submission['artist_name'], inline=True)
            embed.add_field(name="Song", value=submission['song_name'], inline=True)
            embed.add_field(name="User ID", value=submission['user_id'], inline=True)
            
            if submission['link_or_file'].startswith('http'):
                embed.add_field(name="Link", value=f"[Click Here]({submission['link_or_file']})", inline=False)
            else:
                embed.add_field(name="File", value=submission['link_or_file'], inline=False)

            if submission.get('tiktok_username'):
                embed.add_field(name="TikTok", value=submission['tiktok_username'], inline=True)

            if submission.get('note'):
                embed.add_field(name="Note", value=submission['note'], inline=False)
            
            embed.set_footer(text=f"Originally submitted on {submission['submission_time']} | Luxurious Radio By Emerald Beats")
            embed.timestamp = discord.utils.utcnow()
            
            await bookmark_channel.send(embed=embed)
            
            embed_confirm = discord.Embed(
                title="✅ Submission Bookmarked",
                description=f"Submission `#{public_id}` has been bookmarked to {bookmark_channel.mention}",
                color=discord.Color.green()
            )
            await interaction.response.send_message(embed=embed_confirm, ephemeral=True)
            
        except Exception as e:
            await interaction.response.send_message(f"❌ Error bookmarking submission: {str(e)}", ephemeral=True)

    @app_commands.command(name="selfheal", description="[ADMIN] Manually run the self-healing and cleaning routine for all queue channels.")
    @is_admin()
    async def self_heal(self, interaction: discord.Interaction):
        """Forces the bot to re-initialize all queue views, cleaning up old messages and ensuring views are active."""
        await interaction.response.defer(ephemeral=True, thinking=True)

        queue_view_cog = self.bot.get_cog('QueueViewCog')
        if not queue_view_cog:
            await interaction.followup.send("❌ Critical error: The `QueueViewCog` is not loaded.", ephemeral=True)
            return

        try:
            await queue_view_cog.initialize_all_views()
            await interaction.followup.send("✅ Self-healing routine completed successfully.", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"❌ An error occurred during the self-healing routine: {e}", ephemeral=True)

    @app_commands.command(name="showsettings", description="[ADMIN] Display all current bot channel configurations.")
    @is_admin()
    async def show_settings(self, interaction: discord.Interaction):
        """Displays all configured channels for queues and other features."""
        await interaction.response.defer(ephemeral=True)

        try:
            # Fetch all settings
            all_channel_settings = await self.bot.db.get_all_channel_settings()
            bot_settings = await self.bot.db.get_all_bot_settings()

            embed = discord.Embed(title="⚙️ Bot Channel Settings", color=discord.Color.blue())
            embed.description = "Here are all the currently configured channels for the bot."

            # Queue Channels
            queue_lines_info = []
            if all_channel_settings:
                for setting in all_channel_settings:
                    channel_id = setting.get('channel_id')
                    channel_mention = f"<#{channel_id}>" if channel_id else "Not Set"
                    queue_lines_info.append(f"**{setting['queue_line']}**: {channel_mention} `(ID: {channel_id})`")
                embed.add_field(name="🎶 Queue Lines", value="\n".join(queue_lines_info), inline=False)
            else:
                embed.add_field(name="🎶 Queue Lines", value="No queue line channels have been set.", inline=False)

            # Other Channels
            other_channels_info = []
            bookmark_id = bot_settings.get('bookmark_channel_id')
            now_playing_id = bot_settings.get('now_playing_channel_id')
            submission_channel_id = await self.bot.db.get_submission_channel()

            bookmark_mention = f"<#{bookmark_id}> `(ID: {bookmark_id})`" if bookmark_id else "Not Set"
            now_playing_mention = f"<#{now_playing_id}> `(ID: {now_playing_id})`" if now_playing_id else "Not Set"
            submission_mention = f"<#{submission_channel_id}> `(ID: {submission_channel_id})`" if submission_channel_id else "Not Set"

            other_channels_info.append(f"**Bookmark Channel**: {bookmark_mention}")
            other_channels_info.append(f"**'Now Playing' Channel**: {now_playing_mention}")
            other_channels_info.append(f"**Submission Channel**: {submission_mention}")

            embed.add_field(name="📁 Other Channels", value="\n".join(other_channels_info), inline=False)

            embed.set_footer(text="Use the respective /set... commands to change these settings.")

            await interaction.followup.send(embed=embed, ephemeral=True)

        except Exception as e:
            await interaction.followup.send(f"❌ An error occurred while fetching settings: {e}", ephemeral=True)

    @app_commands.command(name="cleanqueues", description="[ADMIN] Remove old, unused queue line settings from the database.")
    @is_admin()
    async def clean_queues(self, interaction: discord.Interaction):
        """Removes stale queue line settings that are no longer part of the bot's valid queues."""
        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            removed_count = await self.bot.db.clear_stale_queue_lines()
            if removed_count > 0:
                embed = discord.Embed(
                    title="✅ Stale Queues Cleaned",
                    description=f"Successfully removed {removed_count} old queue line setting(s) from the database.",
                    color=discord.Color.green()
                )
            else:
                embed = discord.Embed(
                    title="👍 No Stale Queues Found",
                    description="Your queue line settings are all up-to-date. No cleanup was needed.",
                    color=discord.Color.blue()
                )
            await interaction.followup.send(embed=embed, ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"❌ An error occurred during cleanup: {e}", ephemeral=True)



async def setup(bot):
    """Setup function for the cog"""
    await bot.add_cog(AdminCog(bot))