"""
Queue Cog - Handles queue display and user queue commands
"""

import discord
from discord.ext import commands
from discord import app_commands, ui
from database import QueueLine
from typing import Optional
import functools

# --- UI Components for moving submissions ---

class LineSelect(ui.Select):
    """A select menu for choosing a new queue line."""
    def __init__(self, bot: commands.Bot, submission_id: int):
        self.bot = bot
        self.submission_id = submission_id

        options = [
            discord.SelectOption(label="BackToBack", value=QueueLine.BACKTOBACK.value),
            discord.SelectOption(label="DoubleSkip", value=QueueLine.DOUBLESKIP.value),
            discord.SelectOption(label="Skip", value=QueueLine.SKIP.value),
        ]

        super().__init__(placeholder="Choose a destination line...", options=options)

    async def callback(self, interaction: discord.Interaction):
        """Handle the selection of a new line."""
        if not interaction.user.guild_permissions.manage_guild:
            await interaction.response.send_message("❌ You don't have permission to do this.", ephemeral=True)
            return

        target_line = self.values[0]
        try:
            success = await self.bot.db.move_submission(self.submission_id, target_line)

            if success:
                queue_cog = self.bot.get_cog('QueueCog')
                await queue_cog.update_queue_display(QueueLine.FREE.value)
                await queue_cog.update_queue_display(target_line)
                await interaction.response.edit_message(content=f"✅ Moved submission `#{self.submission_id}` to **{target_line}**.", view=None)
            else:
                await interaction.response.edit_message(content=f"❌ Submission `#{self.submission_id}` not found.", view=None)
        except Exception as e:
            await interaction.response.edit_message(content=f"❌ An error occurred: {str(e)}", view=None)

class MoveActionView(ui.View):
    """A view that contains the LineSelect menu for a specific submission."""
    def __init__(self, bot: commands.Bot, submission_id: int):
        super().__init__(timeout=180)
        self.add_item(LineSelect(bot, submission_id))

class FreeQueueActionsView(ui.View):
    """A view containing buttons to move submissions from the free queue."""
    def __init__(self, bot: commands.Bot, submissions: list):
        super().__init__(timeout=None)
        self.bot = bot

        for i, sub in enumerate(submissions):
            if i >= 25:  # Discord limit of 25 components per message
                break

            # Create a button for each submission
            button = ui.Button(
                style=discord.ButtonStyle.secondary,
                label=f"Move #{sub['id']}",
                custom_id=f"move_{sub['id']}"
            )

            # Define the callback using a closure and functools.partial
            async def button_callback(interaction: discord.Interaction, sub_id: int):
                if not interaction.user.guild_permissions.manage_guild:
                    await interaction.response.send_message("❌ You don't have permission for this.", ephemeral=True)
                    return

                # Show the line selection dropdown in an ephemeral message
                view = MoveActionView(self.bot, sub_id)
                await interaction.response.send_message(f"Move submission `#{sub_id}` to which line?", view=view, ephemeral=True)

            button.callback = functools.partial(button_callback, sub_id=sub['id'])
            self.add_item(button)

# -----------------------------------------

class QueueCog(commands.Cog):
    """Cog for queue management and display"""
    
    def __init__(self, bot):
        self.bot = bot
    
    async def update_queue_display(self, queue_line: str):
        """Update the pinned embed message for a queue line"""
        try:
            # Get channel settings for this line
            channel_settings = await self.bot.db.get_channel_for_line(queue_line)
            if not channel_settings or not channel_settings['channel_id']:
                return  # No channel set for this line
            
            # Get the channel
            channel = self.bot.get_channel(channel_settings['channel_id'])
            if not channel:
                return
            
            # Get submissions for this line
            submissions = await self.bot.db.get_queue_submissions(queue_line)
            
            # Create embed
            embed = discord.Embed(
                title=f"🎵 {queue_line} Queue Line",
                color=self._get_line_color(queue_line)
            )
            
            if not submissions:
                embed.description = "No submissions in this line."
            else:
                description = ""
                for i, sub in enumerate(submissions, 1):
                    link_text = f" ([Link]({sub['link_or_file']}))" if sub['link_or_file'].startswith('http') else ""
                    description += f"**{i}.** `#{sub['id']}` {sub['username']} – *{sub['artist_name']} – {sub['song_name']}*{link_text}\n"
                
                embed.description = description
            
            embed.set_footer(text=f"Total submissions: {len(submissions)} | Last updated")
            embed.timestamp = discord.utils.utcnow()
            
            # Determine the view to use
            view = discord.ui.View() # Default empty view
            if queue_line == QueueLine.FREE.value and submissions:
                view = FreeQueueActionsView(self.bot, submissions)

            # Update or create pinned message
            if channel_settings['pinned_message_id']:
                try:
                    message = await channel.fetch_message(channel_settings['pinned_message_id'])
                    await message.edit(embed=embed, view=view)
                except discord.NotFound:
                    # Message was deleted, create new one
                    await self._create_new_pinned_message(channel, embed, queue_line, view)
            else:
                # No pinned message exists, create one
                await self._create_new_pinned_message(channel, embed, queue_line, view)
                
        except Exception as e:
            print(f"Error updating queue display for {queue_line}: {e}")
    
    async def _create_new_pinned_message(self, channel, embed, queue_line, view: ui.View):
        """Create a new pinned message for the queue"""
        try:
            message = await channel.send(embed=embed, view=view)
            await message.pin()
            await self.bot.db.update_pinned_message(queue_line, message.id)
        except Exception as e:
            print(f"Error creating pinned message: {e}")
    
    def _get_line_color(self, queue_line: str) -> discord.Color:
        """Get color for queue line embed"""
        colors = {
            QueueLine.BACKTOBACK.value: discord.Color.red(),
            QueueLine.DOUBLESKIP.value: discord.Color.orange(),
            QueueLine.SKIP.value: discord.Color.yellow(),
            QueueLine.FREE.value: discord.Color.green(),
            QueueLine.CALLS_PLAYED.value: discord.Color.purple()
        }
        return colors.get(queue_line, discord.Color.blue())
    
    @app_commands.command(name="help", description="Show help information about the music queue bot")
    async def help_command(self, interaction: discord.Interaction):
        """Display help information"""
        embed = discord.Embed(
            title="🎵 Music Queue Bot Help",
            description="TikTok-style music review queue system",
            color=discord.Color.blue()
        )
        
        # User commands
        embed.add_field(
            name="📝 User Commands",
            value=(
                "**/submit** - Submit music link for review (opens form)\n"
                "**/submitfile** - Submit MP3/audio file for review\n"
                "**/myqueue** - View your active submissions\n"
                "**/help** - Show this help message"
            ),
            inline=False
        )
        
        # Queue lines explanation
        embed.add_field(
            name="🎯 Queue Lines (Priority Order)",
            value=(
                "**BackToBack** - Highest priority\n"
                "**DoubleSkip** - High priority\n"
                "**Skip** - Medium priority\n"
                "**Free** - Standard submissions (1 per user)\n"
                "**Calls Played** - Archive of reviewed tracks"
            ),
            inline=False
        )
        
        # Admin commands (if user has permissions)
        if (
            hasattr(interaction.user, 'guild_permissions') and 
            interaction.user.guild_permissions and
            interaction.user.guild_permissions.manage_guild
        ):
            embed.add_field(
                name="🔧 Admin Commands",
                value=(
                    "**/setline** - Set channel for queue line\n"
                    "**/move** - Move submission between lines\n"
                    "**/remove** - Remove a submission\n"
                    "**/next** - Get next submission to review"
                ),
                inline=False
            )
        
        embed.set_footer(text="Music submissions are reviewed in priority order")
        await interaction.response.send_message(embed=embed, ephemeral=True)

async def setup(bot):
    """Setup function for the cog"""
    await bot.add_cog(QueueCog(bot))