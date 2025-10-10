"""
Passive Submission Cog - Listens for direct audio file uploads and music links.
Allows users to submit music by simply uploading or pasting, without using commands.
"""

import discord
from discord.ext import commands
import logging
import re
from typing import Optional, List
from database import QueueLine

# Supported music platforms for passive submissions
SUPPORTED_MUSIC_PLATFORMS = [
    'soundcloud.com',
    'spotify.com',
    'youtube.com',
    'youtu.be',
    'deezer.com',
    'dittomusic.com'
]

# Rejected platforms (for clear error messaging)
REJECTED_PLATFORMS = [
    'music.apple.com',
    'itunes.apple.com',
    'apple.com'
]

# Supported audio file extensions
SUPPORTED_AUDIO_EXTENSIONS = ['.mp3', '.m4a']


class PassiveSubmissionCog(commands.Cog):
    """Cog that listens for passive music submissions via uploads or links."""
    
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.submission_count = 0
        
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Listen for messages containing audio files or music links."""
        
        # Ignore bot messages
        if message.author.bot:
            return
        
        # Ignore messages that are commands (start with /)
        if message.content.startswith('/'):
            return
        
        # Check for audio file attachments
        audio_file = self._get_audio_attachment(message)
        if audio_file:
            await self._process_passive_file_submission(message, audio_file)
            return
        
        # Check for rejected music links first
        rejected_link = self._check_rejected_link(message.content)
        if rejected_link:
            await message.reply(
                "❌ **Invalid file or unsupported link.**\n"
                "Please use a `.mp3` or `.m4a` file, or a recognized music platform link:\n"
                "✅ SoundCloud, Spotify, YouTube, Deezer, Ditto Music",
                delete_after=15
            )
            return
        
        # Check for music links
        music_link = self._get_music_link(message.content)
        if music_link:
            await self._process_passive_link_submission(message, music_link)
            return
    
    def _get_audio_attachment(self, message: discord.Message) -> Optional[discord.Attachment]:
        """Check if message contains a valid audio file attachment."""
        for attachment in message.attachments:
            # Check file extension
            filename_lower = attachment.filename.lower()
            if any(filename_lower.endswith(ext) for ext in SUPPORTED_AUDIO_EXTENSIONS):
                return attachment
            
            # Check if it's an unsupported audio file
            unsupported_audio = ['.wav', '.flac', '.ogg', '.aac', '.wma', '.aiff']
            if any(filename_lower.endswith(ext) for ext in unsupported_audio):
                # This is an audio file but not supported
                return None
        return None
    
    def _check_rejected_link(self, content: str) -> bool:
        """Check if message contains a rejected music platform link."""
        url_pattern = r'https?://[^\s]+'
        urls = re.findall(url_pattern, content)
        
        for url in urls:
            url_lower = url.lower()
            if any(platform in url_lower for platform in REJECTED_PLATFORMS):
                return True
        
        return False
    
    def _get_music_link(self, content: str) -> Optional[str]:
        """Extract and validate music link from message content."""
        # Simple URL extraction pattern
        url_pattern = r'https?://[^\s]+'
        urls = re.findall(url_pattern, content)
        
        for url in urls:
            url_lower = url.lower()
            
            # Check if it's a rejected platform
            if any(platform in url_lower for platform in REJECTED_PLATFORMS):
                return None  # Will be handled separately
            
            # Check if it's a supported platform
            if any(platform in url_lower for platform in SUPPORTED_MUSIC_PLATFORMS):
                return url
        
        return None
    
    async def _process_passive_file_submission(self, message: discord.Message, attachment: discord.Attachment):
        """Process a passive audio file submission."""
        try:
            # Validate file size (Discord max is 25MB for regular users)
            max_size = 25 * 1024 * 1024  # 25MB in bytes
            if attachment.size > max_size:
                await message.reply(
                    "❌ File too large. Maximum size is 25MB.",
                    delete_after=10
                )
                return
            
            # Get user's linked TikTok handle if available
            tiktok_handle = await self._get_user_tiktok_handle(message.author.id)
            has_linked_handle = tiktok_handle is not None
            
            # Create submission data
            submission_data = {
                'artist_name': message.author.display_name,
                'song_name': 'Not Known',
                'link_or_file': attachment.url,
                'note': None,
                'is_skip': False,
                'queue_line': QueueLine.FREE.value
            }
            
            # Add submission to database
            await self.bot.db.add_submission(
                discord_user_id=message.author.id,
                artist_name=submission_data['artist_name'],
                song_name=submission_data['song_name'],
                link_or_file=submission_data['link_or_file'],
                note=submission_data['note'],
                queue_line=submission_data['queue_line'],
                tiktok_username=tiktok_handle
            )
            
            # Dispatch queue update event
            self.bot.dispatch('queue_update')
            
            # Send confirmation message
            confirmation = await self._build_confirmation_message(has_linked_handle)
            await message.reply(confirmation, delete_after=15)
            
            self.submission_count += 1
            logging.info(
                f"Passive file submission: {message.author.display_name} - Not Known "
                f"(user: {message.author.id}, file: {attachment.filename})"
            )
            
        except Exception as e:
            logging.error(f"Error processing passive file submission: {e}", exc_info=True)
            await message.reply(
                "❌ An error occurred while processing your submission. Please try again.",
                delete_after=10
            )
    
    async def _process_passive_link_submission(self, message: discord.Message, link: str):
        """Process a passive music link submission."""
        try:
            # Get user's linked TikTok handle if available
            tiktok_handle = await self._get_user_tiktok_handle(message.author.id)
            has_linked_handle = tiktok_handle is not None
            
            # Create submission data
            submission_data = {
                'artist_name': message.author.display_name,
                'song_name': 'Not Known',
                'link_or_file': link,
                'note': None,
                'is_skip': False,
                'queue_line': QueueLine.FREE.value
            }
            
            # Add submission to database
            await self.bot.db.add_submission(
                discord_user_id=message.author.id,
                artist_name=submission_data['artist_name'],
                song_name=submission_data['song_name'],
                link_or_file=submission_data['link_or_file'],
                note=submission_data['note'],
                queue_line=submission_data['queue_line'],
                tiktok_username=tiktok_handle
            )
            
            # Dispatch queue update event
            self.bot.dispatch('queue_update')
            
            # Send confirmation message
            confirmation = await self._build_confirmation_message(has_linked_handle)
            await message.reply(confirmation, delete_after=15)
            
            self.submission_count += 1
            logging.info(
                f"Passive link submission: {message.author.display_name} - Not Known "
                f"(user: {message.author.id}, link: {link})"
            )
            
        except Exception as e:
            logging.error(f"Error processing passive link submission: {e}", exc_info=True)
            await message.reply(
                "❌ An error occurred while processing your submission. Please try again.",
                delete_after=10
            )
    
    async def _get_user_tiktok_handle(self, discord_user_id: int) -> Optional[str]:
        """Get the user's linked TikTok handle if they have one."""
        async with self.bot.db.pool.acquire() as conn:
            handle = await conn.fetchval(
                "SELECT handle_name FROM tiktok_accounts WHERE linked_discord_id = $1 LIMIT 1",
                discord_user_id
            )
        return handle
    
    async def _build_confirmation_message(self, has_linked_handle: bool) -> str:
        """Build confirmation message based on whether user has linked TikTok handle."""
        message = "✅ **Submission received and added to the queue!**"
        
        if not has_linked_handle:
            message += "\n\n💡 **Tip:** Link your TikTok handle using `/link-tiktok` for added benefits and points tracking."
        
        return message


async def setup(bot: commands.Bot):
    """Load the PassiveSubmissionCog."""
    await bot.add_cog(PassiveSubmissionCog(bot))
    logging.info("PassiveSubmissionCog loaded successfully.")
