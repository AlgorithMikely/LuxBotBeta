import os
import discord
from discord.ext import commands
from dotenv import load_dotenv
import logging
import asyncio
from database import db

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class MusicBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.guilds = True
        intents.members = True

        super().__init__(
            command_prefix='!',
            intents=intents,
            help_command=None
        )

    async def setup_hook(self):
        logger.info("Connecting to database...")
        await db.connect()

        logger.info("Loading cogs...")
        cogs = [
            'cogs.submissions',
            'cogs.queue',
            'cogs.tiktok_integration',
            'cogs.tiktok_linking',
            'cogs.luxury_coins',
            'cogs.persistent_embeds',
            'cogs.admin',
            'cogs.points_sync'
        ]

        for cog in cogs:
            try:
                await self.load_extension(cog)
                logger.info(f"Loaded {cog}")
            except Exception as e:
                logger.error(f"Failed to load {cog}: {e}")

    async def on_ready(self):
        logger.info(f'Bot logged in as {self.user} (ID: {self.user.id})')
        await self.tree.sync()
        logger.info('Command tree synced')

    async def close(self):
        await db.disconnect()
        await super().close()


async def main():
    bot = MusicBot()
    token = os.getenv('DISCORD_BOT_TOKEN')

    if not token:
        logger.error("DISCORD_BOT_TOKEN not found in environment variables")
        return

    try:
        await bot.start(token)
    except KeyboardInterrupt:
        logger.info("Shutting down bot...")
        await bot.close()
    except Exception as e:
        logger.error(f"Error running bot: {e}")
        await bot.close()


if __name__ == "__main__":
    asyncio.run(main())