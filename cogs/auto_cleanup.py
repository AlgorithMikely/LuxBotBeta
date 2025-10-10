
import discord
from discord.ext import commands
import logging
from database import db

logger = logging.getLogger(__name__)

class AutoCleanup(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.monitored_channels = set()
        
    async def cog_load(self):
        """Load monitored channel IDs from database on startup"""
        await self.refresh_monitored_channels()
        logger.info("AutoCleanup cog loaded")
    
    async def refresh_monitored_channels(self):
        """Refresh the set of monitored channel IDs from database"""
        channels = await db.fetch('''
            SELECT channel_id FROM bot_config
            WHERE key IN ('submission_channel', 'queue_channel')
            AND channel_id IS NOT NULL
        ''')
        
        self.monitored_channels = {row['channel_id'] for row in channels}
        logger.info(f"Monitoring channels: {self.monitored_channels}")
    
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Automatically delete unauthorized messages in monitored channels"""
        
        # Ignore bot and system messages
        if message.author.bot:
            return
        
        # Ignore messages outside monitored channels
        if message.channel.id not in self.monitored_channels:
            return
        
        # Skip messages from admins or users with manage_messages permission
        if message.guild:
            perms = message.author.guild_permissions
            if perms.administrator or perms.manage_messages:
                return
            
            # Check if user has a role named "Moderator"
            if any(role.name == "Moderator" for role in message.author.roles):
                return
        
        # Delete unauthorized message silently
        try:
            await message.delete()
            logger.debug(f"Deleted message from {message.author} in {message.channel.name}")
        except discord.Forbidden:
            logger.warning(f"Missing permissions to delete message in {message.channel.name}")
        except discord.HTTPException as e:
            logger.debug(f"Failed to delete message: {e}")

async def setup(bot):
    await bot.add_cog(AutoCleanup(bot))
