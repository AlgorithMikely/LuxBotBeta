"""
Skip Submission Cog - Handles user submissions for skip lines via Discord UI Modal
"""

import discord
from discord.ext import commands
from discord import app_commands
from database import QueueLine

class SkipSubmissionModal(discord.ui.Modal, title='Submit Music for Priority Review'):
    """Modal form for skip line music submissions"""

    def __init__(self, bot):
        super().__init__()
        self.bot = bot

    artist_name = discord.ui.TextInput(
        label='Artist Name',
        placeholder='Enter the artist name...',
        required=True,
        max_length=100
    )

    song_name = discord.ui.TextInput(
        label='Song Name',
        placeholder='Enter the song title...',
        required=True,
        max_length=100
    )

    link_or_file = discord.ui.TextInput(
        label='Music Link',
        placeholder='Paste a URL (YouTube, Spotify, SoundCloud, etc.)...',
        required=True,
        max_length=500
    )

    async def on_submit(self, interaction: discord.Interaction):
        """Handle form submission"""
        submissions_open = await self.bot.db.are_skip_submissions_open()
        if not submissions_open:
            await interaction.response.send_message(
                "❌ Skip submissions are currently closed. Please try again later.",
                ephemeral=True
            )
            return

        link_value = str(self.link_or_file.value).strip()

        if not (link_value.startswith('http://') or link_value.startswith('https://')):
            await interaction.response.send_message(
                "❌ Please provide a valid URL (YouTube, Spotify, SoundCloud, etc.).",
                ephemeral=True
            )
            return

        if 'music.apple.com' in link_value.lower() or 'itunes.apple.com' in link_value.lower():
            await interaction.response.send_message(
                "❌ Apple Music links are not supported. Please use YouTube, Spotify, SoundCloud, or other supported platforms.",
                ephemeral=True
            )
            return

        try:
            submission_id = await self.bot.db.add_submission(
                user_id=interaction.user.id,
                username=interaction.user.display_name,
                artist_name=str(self.artist_name.value).strip(),
                song_name=str(self.song_name.value).strip(),
                link_or_file=link_value,
                queue_line=QueueLine.UNCONFIRMED.value
            )

            embed = discord.Embed(
                title="✅ Skip Submission Received!",
                description="Your music has been submitted and is awaiting confirmation.",
                color=discord.Color.gold()
            )
            embed.add_field(name="Artist", value=self.artist_name.value, inline=True)
            embed.add_field(name="Song", value=self.song_name.value, inline=True)
            embed.add_field(name="Submission ID", value=f"#{submission_id}", inline=False)
            embed.set_footer(text="You will be notified when an admin confirms your submission.")

            await interaction.response.send_message(embed=embed, ephemeral=True)

        except Exception as e:
            await interaction.response.send_message(
                f"❌ An error occurred while adding your submission: {str(e)}",
                ephemeral=True
            )

class SkipSubmissionCog(commands.Cog):
    """Cog for handling skip music submissions"""

    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="submitskip", description="Submit music for priority review")
    async def submit_skip(self, interaction: discord.Interaction):
        """Open submission modal for skip line submissions"""
        modal = SkipSubmissionModal(self.bot)
        await interaction.response.send_modal(modal)

async def setup(bot):
    """Setup function for the cog"""
    await bot.add_cog(SkipSubmissionCog(bot))