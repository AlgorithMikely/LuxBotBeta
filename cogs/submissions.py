import discord
from discord.ext import commands
from discord import app_commands
import validators
import aiofiles
import os
import uuid
import logging
import asyncio
from database import db
import io
from datetime import datetime

logger = logging.getLogger(__name__)

SUPPORTED_PLATFORMS = ['soundcloud', 'spotify', 'youtube', 'deezer', 'ditto']
REJECTED_PLATFORMS = ['apple', 'itunes']
SUPPORTED_FILE_EXTENSIONS = ['.mp3', '.m4a', '.wav', '.flac']
MAX_FILE_SIZE = 25 * 1024 * 1024


class Submissions(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def get_submission_channel_id(self):
        row = await db.fetchrow(
            "SELECT channel_id FROM bot_config WHERE key = 'submission_channel'"
        )
        return row['channel_id'] if row else None

    def is_supported_platform(self, url: str):
        url_lower = url.lower()
        for platform in SUPPORTED_PLATFORMS:
            if platform in url_lower:
                return True
        for platform in REJECTED_PLATFORMS:
            if platform in url_lower:
                return False
        return False

    async def create_submission(self, user_id: int, username: str, artist_name: str,
                                song_name: str, link_or_file: str, note: str = None,
                                tiktok_username: str = None):
        public_id = str(uuid.uuid4())[:8]

        if not artist_name or artist_name.strip() == '':
            artist_name = username

        if not song_name or song_name.strip() == '':
            song_name = "Not Known"

        await db.execute('''
            INSERT INTO submissions 
            (public_id, user_id, username, artist_name, song_name, link_or_file, 
             queue_line, note, tiktok_username, total_score)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, 0)
        ''', public_id, user_id, username, artist_name, song_name, 
             link_or_file, 'Free', note, tiktok_username)

        self.bot.dispatch('queue_update')
        return public_id

    async def send_confirmation(self, user, channel, public_id: str):
        message = f"✅ Submission received! Your submission ID is: `{public_id}`"
        try:
            await user.send(message)
        except discord.Forbidden:
            await channel.send(f"{user.mention} {message}", delete_after=10)

    async def process_submission(self, user: discord.User, username: str, artist_name: str,
                                 song_name: str, link_or_file: str, channel: discord.TextChannel):
        public_id = await self.create_submission(
            user.id,
            username,
            artist_name,
            song_name,
            link_or_file
        )
        await self.send_confirmation(user, channel, public_id)
        await channel.send(f"✅ Submission successful! ID: `{public_id}`")

    @app_commands.command(name="submit", description="Submit a music link")
    async def submit(self, interaction: discord.Interaction):
        class SubmitModal(discord.ui.Modal, title="Submit Music"):
            link = discord.ui.TextInput(
                label="Music Link",
                placeholder="YouTube, Spotify, SoundCloud, Deezer, or Ditto link",
                required=True
            )
            artist = discord.ui.TextInput(
                label="Artist Name",
                placeholder="Optional - defaults to your username",
                required=False
            )
            title = discord.ui.TextInput(
                label="Song Title",
                placeholder="Optional - defaults to 'Not Known'",
                required=False
            )
            note = discord.ui.TextInput(
                label="Note (Optional)",
                placeholder="Any additional notes",
                required=False,
                style=discord.TextStyle.paragraph
            )
            tiktok_handle = discord.ui.TextInput(
                label="TikTok Handle (Optional)",
                placeholder="Your TikTok username",
                required=False
            )

            async def on_submit(modal_self, modal_interaction: discord.Interaction):
                await modal_interaction.response.defer(ephemeral=True)

                url = modal_self.link.value
                if not validators.url(url):
                    await modal_interaction.followup.send(
                        "❌ Invalid URL provided.", ephemeral=True
                    )
                    return

                cog = interaction.client.get_cog('Submissions')
                if not cog.is_supported_platform(url):
                    if any(p in url.lower() for p in REJECTED_PLATFORMS):
                        await modal_interaction.followup.send(
                            "❌ Apple Music/iTunes links are not supported. Please use Spotify, YouTube, SoundCloud, Deezer, or Ditto.",
                            ephemeral=True
                        )
                        return
                    await modal_interaction.followup.send(
                        "❌ Unsupported platform. Please use YouTube, Spotify, SoundCloud, Deezer, or Ditto.",
                        ephemeral=True
                    )
                    return

                public_id = await cog.create_submission(
                    modal_interaction.user.id,
                    modal_interaction.user.name,
                    modal_self.artist.value or modal_interaction.user.name,
                    modal_self.title.value or "Not Known",
                    url,
                    modal_self.note.value or None,
                    modal_self.tiktok_handle.value or None
                )

                await cog.send_confirmation(
                    modal_interaction.user,
                    modal_interaction.channel,
                    public_id
                )
                await modal_interaction.followup.send(
                    f"✅ Submission successful! ID: `{public_id}`",
                    ephemeral=True
                )

        await interaction.response.send_modal(SubmitModal())

    @app_commands.command(name="submitfile", description="Submit a music file")
    async def submitfile(self, interaction: discord.Interaction):
        class SubmitFileModal(discord.ui.Modal, title="Submit Music File"):
            artist = discord.ui.TextInput(
                label="Artist Name",
                required=True
            )
            title = discord.ui.TextInput(
                label="Song Title",
                required=True
            )
            note = discord.ui.TextInput(
                label="Note (Optional)",
                required=False,
                style=discord.TextStyle.paragraph
            )
            tiktok_handle = discord.ui.TextInput(
                label="TikTok Handle (Optional)",
                placeholder="Your TikTok username",
                required=False
            )

            async def on_submit(modal_self, modal_interaction: discord.Interaction):
                await modal_interaction.response.send_message(
                    "Please upload your audio file (mp3, m4a, wav, flac - max 25MB)",
                    ephemeral=True
                )

                def check(m):
                    return (m.author.id == modal_interaction.user.id and 
                            m.channel.id == modal_interaction.channel.id and
                            len(m.attachments) > 0)

                try:
                    msg = await interaction.client.wait_for('message', check=check, timeout=60.0)
                    attachment = msg.attachments[0]

                    ext = os.path.splitext(attachment.filename)[1].lower()
                    if ext not in SUPPORTED_FILE_EXTENSIONS:
                        await modal_interaction.followup.send(
                            f"❌ Unsupported file type. Please upload: {', '.join(SUPPORTED_FILE_EXTENSIONS)}",
                            ephemeral=True
                        )
                        return

                    if attachment.size > MAX_FILE_SIZE:
                        await modal_interaction.followup.send(
                            "❌ File too large. Maximum size is 25MB.",
                            ephemeral=True
                        )
                        return

                    cog = interaction.client.get_cog('Submissions')
                    public_id = await cog.create_submission(
                        modal_interaction.user.id,
                        modal_interaction.user.name,
                        modal_self.artist.value,
                        modal_self.title.value,
                        attachment.url,
                        modal_self.note.value or None,
                        modal_self.tiktok_handle.value or None
                    )

                    await cog.send_confirmation(
                        modal_interaction.user,
                        modal_interaction.channel,
                        public_id
                    )
                    await msg.delete()

                except asyncio.TimeoutError:
                    await modal_interaction.followup.send(
                        "❌ Timed out waiting for file upload.",
                        ephemeral=True
                    )

        await interaction.response.send_modal(SubmitFileModal())

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return

        submission_channel_id = await db.fetchval(
            "SELECT channel_id FROM bot_config WHERE key = 'submission_channel'"
        )

        if not submission_channel_id or message.channel.id != submission_channel_id:
            return

        if message.attachments:
            # Get archive channel configuration
            archive_channel_id = await db.fetchval(
                "SELECT channel_id FROM bot_config WHERE key = 'archive_channel'"
            )

            if not archive_channel_id:
                logger.warning("Archive channel not configured, skipping file archiving")
                file_url = message.attachments[0].url
            else:
                archive_channel = self.bot.get_channel(archive_channel_id)

                if not archive_channel:
                    logger.error(f"Archive channel {archive_channel_id} not found")
                    file_url = message.attachments[0].url
                else:
                    try:
                        # Copy file to archive channel
                        attachment = message.attachments[0]
                        file_bytes = await attachment.read()
                        buffer = io.BytesIO(file_bytes)
                        new_file = discord.File(buffer, filename=attachment.filename)

                        archive_message = await archive_channel.send(
                            f"Archived submission from {message.author.mention} ({message.author.name})",
                            file=new_file
                        )

                        # Use the new permanent URL
                        file_url = archive_message.attachments[0].url
                        logger.info(f"File archived: {attachment.filename} -> {file_url}")
                    except discord.errors.Forbidden:
                        logger.error("Bot lacks permissions to archive file")
                        file_url = message.attachments[0].url
                    except Exception as e:
                        logger.error(f"Error archiving file: {e}")
                        file_url = message.attachments[0].url

            await self.process_submission(
                message.author,
                message.author.name,
                "Unknown Artist",
                "Unknown Song",
                file_url,
                message.channel
            )

            # Delete original message after processing
            try:
                await message.delete()
                logger.info(f"Deleted original submission message from {message.author}")
            except discord.errors.Forbidden:
                logger.warning("Bot lacks permission to delete messages")
            except Exception as e:
                logger.error(f"Error deleting message: {e}")

            return

        for word in message.content.split():
            if validators.url(word):
                if self.is_supported_platform(word):
                    public_id = await self.create_submission(
                        message.author.id,
                        message.author.name,
                        message.author.name,
                        "Not Known",
                        word
                    )
                    await self.send_confirmation(message.author, message.channel, public_id)
                    await message.delete()
                    return
                elif any(p in word.lower() for p in REJECTED_PLATFORMS):
                    await message.delete()
                    await message.channel.send(
                        f"{message.author.mention} Apple Music/iTunes links are not supported.",
                        delete_after=10
                    )
                    return

        if message.attachments:
            for attachment in message.attachments:
                ext = os.path.splitext(attachment.filename)[1].lower()
                if ext in SUPPORTED_FILE_EXTENSIONS:
                    if attachment.size <= MAX_FILE_SIZE:
                        public_id = await self.create_submission(
                            message.author.id,
                            message.author.name,
                            message.author.name,
                            attachment.filename,
                            attachment.url
                        )
                        await self.send_confirmation(message.author, message.channel, public_id)
                        await message.delete()
                        return


async def setup(bot):
    await bot.add_cog(Submissions(bot))