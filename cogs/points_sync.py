import discord
from discord.ext import commands, tasks
import logging
from database import db
import json
import aiofiles
from datetime import datetime
import os

logger = logging.getLogger(__name__)


class PointsSync(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.sync_scores.start()
        self.hourly_backup.start()

    def cog_unload(self):
        self.sync_scores.cancel()
        self.hourly_backup.cancel()

    @tasks.loop(seconds=30)
    async def sync_scores(self):
        try:
            submissions = await db.fetch('''
                SELECT s.id, s.user_id, s.tiktok_username
                FROM submissions s
                WHERE s.queue_line = 'Free' AND s.played_time IS NULL
            ''')
            
            for sub in submissions:
                total_score = 0.0
                
                user_points = await db.fetchval(
                    'SELECT points FROM user_points WHERE user_id = $1',
                    sub['user_id']
                )
                
                if user_points:
                    total_score += user_points
                
                if sub['tiktok_username']:
                    tiktok_points = await db.fetchval(
                        'SELECT points FROM tiktok_accounts WHERE handle_name = $1',
                        sub['tiktok_username']
                    )
                    
                    if tiktok_points:
                        total_score += tiktok_points
                
                await db.execute(
                    'UPDATE submissions SET total_score = $1 WHERE id = $2',
                    total_score, sub['id']
                )
                
        except Exception as e:
            logger.error(f"Error in sync_scores: {e}")

    @sync_scores.before_loop
    async def before_sync_scores(self):
        await self.bot.wait_until_ready()

    @tasks.loop(hours=1)
    async def hourly_backup(self):
        try:
            os.makedirs('backups', exist_ok=True)
            
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            
            user_points = await db.fetch('SELECT * FROM user_points')
            user_points_data = [dict(row) for row in user_points]
            
            async with aiofiles.open(f'backups/user_points_{timestamp}.json', 'w') as f:
                await f.write(json.dumps(user_points_data, indent=2))
            
            tiktok_accounts = await db.fetch('SELECT * FROM tiktok_accounts')
            tiktok_data = []
            for row in tiktok_accounts:
                data = dict(row)
                data['first_seen'] = data['first_seen'].isoformat() if data['first_seen'] else None
                data['last_seen'] = data['last_seen'].isoformat() if data['last_seen'] else None
                tiktok_data.append(data)
            
            async with aiofiles.open(f'backups/tiktok_accounts_{timestamp}.json', 'w') as f:
                await f.write(json.dumps(tiktok_data, indent=2))
            
            logger.info(f"Hourly backup completed: {timestamp}")
            
            backup_files = sorted([f for f in os.listdir('backups') if f.endswith('.json')])
            if len(backup_files) > 48:
                for old_file in backup_files[:-48]:
                    os.remove(f'backups/{old_file}')
                    
        except Exception as e:
            logger.error(f"Error in hourly_backup: {e}")

    @hourly_backup.before_loop
    async def before_hourly_backup(self):
        await self.bot.wait_until_ready()


async def setup(bot):
    await bot.add_cog(PointsSync(bot))
