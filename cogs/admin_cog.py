"""
Admin Cog - Handles administrative commands for queue management
"""

import discord
import os
from discord.ext import commands
from discord import app_commands
from database import QueueLine
from typing import Optional

class AdminCog(commands.Cog):
    """Cog for administrative queue management"""
    
    def __init__(self, bot):
        self.bot = bot
    
    def _has_admin_permissions(self, interaction: discord.Interaction) -> bool:
        """Check if user has admin permissions"""
        return (
            hasattr(interaction.user, 'guild_permissions') and 
            interaction.user.guild_permissions and
            interaction.user.guild_permissions.manage_guild
        )
    
    @app_commands.command(name="setline", description="Set the channel for a queue line")
    @app_commands.describe(
        line="The queue line to configure",
        channel="The text channel to use for this line"
    )
    @app_commands.choices(line=[
        app_commands.Choice(name="BackToBack", value="BackToBack"),
        app_commands.Choice(name="DoubleSkip", value="DoubleSkip"),
        app_commands.Choice(name="Skip", value="Skip"),
        app_commands.Choice(name="Free", value="Free"),
        app_commands.Choice(name="Calls Played", value="Calls Played")
    ])
    async def set_line(self, interaction: discord.Interaction, line: str, channel: discord.TextChannel):
        """Set the channel for a queue line"""
        if not self._has_admin_permissions(interaction):
            await interaction.response.send_message(
                "❌ You don't have permission to use this command.", 
                ephemeral=True
            )
            return
        
        try:
            # Set channel for line
            await self.bot.db.set_channel_for_line(line, channel.id)
            
            # Update queue display
            if hasattr(self.bot, 'get_cog') and self.bot.get_cog('QueueCog'):
                queue_cog = self.bot.get_cog('QueueCog')
                await queue_cog.update_queue_display(line)
            
            embed = discord.Embed(
                title="✅ Line Channel Set",
                description=f"**{line}** line is now set to {channel.mention}",
                color=discord.Color.green()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            
        except Exception as e:
            await interaction.response.send_message(
                f"❌ Error setting line channel: {str(e)}", 
                ephemeral=True
            )
    
    @app_commands.command(name="move", description="Move a submission to a different queue line")
    @app_commands.describe(
        submission_id="The ID of the submission to move",
        target_line="The target queue line"
    )
    @app_commands.choices(target_line=[
        app_commands.Choice(name="BackToBack", value="BackToBack"),
        app_commands.Choice(name="DoubleSkip", value="DoubleSkip"),
        app_commands.Choice(name="Skip", value="Skip"),
        app_commands.Choice(name="Free", value="Free"),
        app_commands.Choice(name="Calls Played", value="Calls Played")
    ])
    async def move_submission(self, interaction: discord.Interaction, submission_id: int, target_line: str):
        """Move a submission between queue lines"""
        if not self._has_admin_permissions(interaction):
            await interaction.response.send_message(
                "❌ You don't have permission to use this command.", 
                ephemeral=True
            )
            return
        
        try:
            # Move the submission
            success = await self.bot.db.move_submission(submission_id, target_line)
            
            if success:
                # Update queue displays for all lines
                if hasattr(self.bot, 'get_cog') and self.bot.get_cog('QueueCog'):
                    queue_cog = self.bot.get_cog('QueueCog')
                    for line in QueueLine:
                        await queue_cog.update_queue_display(line.value)
                
                embed = discord.Embed(
                    title="✅ Submission Moved",
                    description=f"Submission #{submission_id} has been moved to **{target_line}** line.",
                    color=discord.Color.green()
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
            else:
                await interaction.response.send_message(
                    f"❌ Submission #{submission_id} not found.", 
                    ephemeral=True
                )
                
        except Exception as e:
            await interaction.response.send_message(
                f"❌ Error moving submission: {str(e)}", 
                ephemeral=True
            )
    
    @app_commands.command(name="remove", description="Remove a submission from the queue")
    @app_commands.describe(submission_id="The ID of the submission to remove")
    async def remove_submission(self, interaction: discord.Interaction, submission_id: int):
        """Remove a submission from the queue"""
        if not self._has_admin_permissions(interaction):
            await interaction.response.send_message(
                "❌ You don't have permission to use this command.", 
                ephemeral=True
            )
            return
        
        try:
            # Remove the submission
            success = await self.bot.db.remove_submission(submission_id)
            
            if success:
                # Update queue displays for all lines
                if hasattr(self.bot, 'get_cog') and self.bot.get_cog('QueueCog'):
                    queue_cog = self.bot.get_cog('QueueCog')
                    for line in QueueLine:
                        await queue_cog.update_queue_display(line.value)
                
                embed = discord.Embed(
                    title="✅ Submission Removed",
                    description=f"Submission #{submission_id} has been removed from the queue.",
                    color=discord.Color.green()
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
            else:
                await interaction.response.send_message(
                    f"❌ Submission #{submission_id} not found.", 
                    ephemeral=True
                )
                
        except Exception as e:
            await interaction.response.send_message(
                f"❌ Error removing submission: {str(e)}", 
                ephemeral=True
            )
    
    @app_commands.command(name="setsubmissionchannel", description="Set the channel for submissions (auto-moderated)")
    @app_commands.describe(channel="The text channel to use for submissions")
    async def set_submission_channel(self, interaction: discord.Interaction, channel: discord.TextChannel):
        """Set the channel for submissions"""
        if not self._has_admin_permissions(interaction):
            await interaction.response.send_message(
                "❌ You don't have permission to use this command.", 
                ephemeral=True
            )
            return
        
        try:
            # Set submission channel
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
    async def next_submission(self, interaction: discord.Interaction):
        """Get the next submission following priority order"""
        if not self._has_admin_permissions(interaction):
            await interaction.response.send_message(
                "❌ You don't have permission to use this command.",
                ephemeral=True
            )
            return

        try:
            # Atomically take the next submission and move it to Calls Played
            next_sub = await self.bot.db.take_next_to_calls_played()

            if not next_sub:
                embed = discord.Embed(
                    title="📭 Queue Empty",
                    description="No submissions are currently in the queue.",
                    color=discord.Color.blue()
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return

            # Create embed for the taken submission
            embed = discord.Embed(
                title="🎵 Now Playing - Moved to Calls Played",
                description=f"Moved from **{next_sub['original_line']}** line to **Calls Played**",
                color=discord.Color.gold()
            )

            embed.add_field(name="Submission ID", value=f"#{next_sub['id']}", inline=True)
            embed.add_field(name="Original Line", value=next_sub['original_line'], inline=True)
            embed.add_field(name="Submitted By", value=next_sub['username'], inline=True)
            embed.add_field(name="Artist", value=next_sub['artist_name'], inline=True)
            embed.add_field(name="Song", value=next_sub['song_name'], inline=True)
            
            link_or_file = next_sub['link_or_file']

            # Add web player link for file uploads, and the original link for all submissions
            if link_or_file.startswith('https://cdn.discordapp.com'):
                # This should be the public IP or domain of the machine running the bot
                # You can set this in your .env file as WEB_PLAYER_URL
                base_url = os.getenv('WEB_PLAYER_URL', 'http://127.0.0.1:8000')
                player_url = f"{base_url}/play/{next_sub['id']}"
                embed.add_field(name="▶️ Web Player", value=f"[Click to Play]({player_url})", inline=False)
                embed.add_field(name="Source File", value=f"[Download]({link_or_file})", inline=False)
            elif link_or_file.startswith('http'):
                embed.add_field(name="Source Link", value=f"[Click Here]({link_or_file})", inline=False)
            else:
                # Fallback for non-http data, though this shouldn't happen
                embed.add_field(name="File Info", value=link_or_file, inline=False)

            embed.set_footer(text=f"Submitted on {next_sub['submission_time']}")

            # Send to admin who used the command
            await interaction.response.send_message(embed=embed, ephemeral=True)

            # Update queue displays for both the origin line and Calls Played
            if hasattr(self.bot, 'get_cog') and self.bot.get_cog('QueueCog'):
                queue_cog = self.bot.get_cog('QueueCog')
                await queue_cog.update_queue_display(next_sub['original_line'])
                await queue_cog.update_queue_display(QueueLine.CALLS_PLAYED.value)

            # Also send to DM if possible
            try:
                await interaction.user.send(embed=embed)
            except discord.Forbidden:
                pass  # User has DMs disabled

        except Exception as e:
            await interaction.response.send_message(
                f"❌ Error getting next submission: {str(e)}",
                ephemeral=True
            )
    
    @app_commands.command(name="opensubmissions", description="Open submissions for users")
    async def open_submissions(self, interaction: discord.Interaction):
        """Open submissions"""
        if not self._has_admin_permissions(interaction):
            await interaction.response.send_message(
                "❌ You don't have permission to use this command.", 
                ephemeral=True
            )
            return
        
        try:
            await self.bot.db.set_submissions_status(True)
            
            embed = discord.Embed(
                title="✅ Submissions Opened",
                description="Users can now submit music using `/submit` and `/submitfile` commands.",
                color=discord.Color.green()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            
        except Exception as e:
            await interaction.response.send_message(
                f"❌ Error opening submissions: {str(e)}", 
                ephemeral=True
            )
    
    @app_commands.command(name="closesubmissions", description="Close submissions for users")
    async def close_submissions(self, interaction: discord.Interaction):
        """Close submissions"""
        if not self._has_admin_permissions(interaction):
            await interaction.response.send_message(
                "❌ You don't have permission to use this command.", 
                ephemeral=True
            )
            return
        
        try:
            await self.bot.db.set_submissions_status(False)
            
            embed = discord.Embed(
                title="🚫 Submissions Closed",
                description="Users can no longer submit music. Use `/opensubmissions` to re-enable.",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            
        except Exception as e:
            await interaction.response.send_message(
                f"❌ Error closing submissions: {str(e)}", 
                ephemeral=True
            )
    
    @app_commands.command(name="clearfree", description="Clear all submissions from the Free line")
    async def clear_free_line(self, interaction: discord.Interaction):
        """Clear all submissions from the Free line"""
        if not self._has_admin_permissions(interaction):
            await interaction.response.send_message(
                "❌ You don't have permission to use this command.", 
                ephemeral=True
            )
            return
        
        try:
            cleared_count = await self.bot.db.clear_free_line()
            
            # Update queue display for Free line
            if hasattr(self, 'bot') and hasattr(self.bot, 'get_cog') and self.bot.get_cog('QueueCog'):
                queue_cog = self.bot.get_cog('QueueCog')
                await queue_cog.update_queue_display(QueueLine.FREE.value)
            
            embed = discord.Embed(
                title="🗑️ Free Line Cleared",
                description=f"Removed {cleared_count} submission{'s' if cleared_count != 1 else ''} from the Free line.",
                color=discord.Color.orange()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            
        except Exception as e:
            await interaction.response.send_message(
                f"❌ Error clearing Free line: {str(e)}", 
                ephemeral=True
            )

    @app_commands.command(name="openskip", description="Open skip submissions for users")
    async def open_skip_submissions(self, interaction: discord.Interaction):
        """Open skip submissions"""
        if not self._has_admin_permissions(interaction):
            await interaction.response.send_message(
                "❌ You don't have permission to use this command.",
                ephemeral=True
            )
            return

        try:
            await self.bot.db.set_skip_submissions_status(True)
            embed = discord.Embed(
                title="✅ Skip Submissions Opened",
                description="Users can now submit music for the skip line using `/submitskip`.",
                color=discord.Color.green()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(
                f"❌ Error opening skip submissions: {str(e)}",
                ephemeral=True
            )

    @app_commands.command(name="closeskip", description="Close skip submissions for users")
    async def close_skip_submissions(self, interaction: discord.Interaction):
        """Close skip submissions"""
        if not self._has_admin_permissions(interaction):
            await interaction.response.send_message(
                "❌ You don't have permission to use this command.",
                ephemeral=True
            )
            return

        try:
            await self.bot.db.set_skip_submissions_status(False)
            embed = discord.Embed(
                title="🚫 Skip Submissions Closed",
                description="Users can no longer submit to the skip line. Use `/openskip` to re-enable.",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(
                f"❌ Error closing skip submissions: {str(e)}",
                ephemeral=True
            )

    @app_commands.command(name="confirmsubmission", description="Confirm a pending skip submission and move it to a priority line")
    @app_commands.describe(
        submission_id="The ID of the submission to confirm",
        target_line="The priority line to move the submission to"
    )
    @app_commands.choices(target_line=[
        app_commands.Choice(name="Skip", value="Skip"),
        app_commands.Choice(name="DoubleSkip", value="DoubleSkip"),
        app_commands.Choice(name="BackToBack", value="BackToBack"),
    ])
    async def confirm_submission(self, interaction: discord.Interaction, submission_id: int, target_line: str):
        """Confirm a submission and move it to a skip line"""
        if not self._has_admin_permissions(interaction):
            await interaction.response.send_message(
                "❌ You don't have permission to use this command.",
                ephemeral=True
            )
            return

        try:
            submission = await self.bot.db.get_submission_by_id(submission_id)

            if not submission:
                await interaction.response.send_message(
                    f"❌ Submission #{submission_id} not found.",
                    ephemeral=True
                )
                return

            if submission['queue_line'] != QueueLine.UNCONFIRMED.value:
                await interaction.response.send_message(
                    f"❌ Submission #{submission_id} is not in the Unconfirmed line. It is currently in the **{submission['queue_line']}** line.",
                    ephemeral=True
                )
                return

            success = await self.bot.db.move_submission(submission_id, target_line)

            if success:
                # Update queue displays
                if hasattr(self.bot, 'get_cog') and self.bot.get_cog('QueueCog'):
                    queue_cog = self.bot.get_cog('QueueCog')
                    await queue_cog.update_queue_display(QueueLine.UNCONFIRMED.value)
                    await queue_cog.update_queue_display(target_line)

                embed = discord.Embed(
                    title="✅ Submission Confirmed",
                    description=f"Submission #{submission_id} has been moved to the **{target_line}** line.",
                    color=discord.Color.green()
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)

                # Notify the user
                user = self.bot.get_user(submission['user_id'])
                if user:
                    try:
                        user_embed = discord.Embed(
                            title="🎉 Your Submission is Confirmed!",
                            description=f"Your submission for **{submission['artist_name']} - {submission['song_name']}** has been confirmed and moved to the **{target_line}** line.",
                            color=discord.Color.green()
                        )
                        await user.send(embed=user_embed)
                    except discord.Forbidden:
                        pass  # User has DMs disabled
            else:
                await interaction.response.send_message(
                    f"❌ Failed to move submission #{submission_id}.",
                    ephemeral=True
                )

        except Exception as e:
            await interaction.response.send_message(
                f"❌ Error confirming submission: {str(e)}",
                ephemeral=True
            )


async def setup(bot):
    """Setup function for the cog"""
    await bot.add_cog(AdminCog(bot))