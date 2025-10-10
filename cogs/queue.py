import discord
from discord.ext import commands
from discord import app_commands
import logging
from database import db
from typing import Optional

logger = logging.getLogger(__name__)

QUEUE_PRIORITY = {
    '25+ Skip': 1,
    '20 Skip': 2,
    '15 Skip': 3,
    '10 Skip': 4,
    '5 Skip': 5,
    'Free': 6,
    'Pending Skips': 7,
    'Songs Played': 8,
    'Removed': 9
}


class Queue(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    def get_priority(self, queue_line: str) -> int:
        return QUEUE_PRIORITY.get(queue_line, 999)

    async def get_next_submission(self):
        async with db.pool.acquire() as conn:
            async with conn.transaction():
                for queue_line in sorted(QUEUE_PRIORITY.keys(), key=lambda x: QUEUE_PRIORITY[x]):
                    if queue_line in ['Pending Skips', 'Songs Played', 'Removed']:
                        continue
                    
                    if queue_line == 'Free':
                        submission = await conn.fetchrow('''
                            SELECT * FROM submissions
                            WHERE queue_line = 'Free' AND played_time IS NULL
                            ORDER BY total_score DESC, submission_time ASC
                            LIMIT 1
                            FOR UPDATE SKIP LOCKED
                        ''')
                    else:
                        submission = await conn.fetchrow('''
                            SELECT * FROM submissions
                            WHERE queue_line = $1 AND played_time IS NULL
                            ORDER BY submission_time ASC
                            LIMIT 1
                            FOR UPDATE SKIP LOCKED
                        ''', queue_line)
                    
                    if submission:
                        await conn.execute('''
                            UPDATE submissions
                            SET queue_line = 'Songs Played', played_time = NOW()
                            WHERE id = $1
                        ''', submission['id'])
                        
                        if queue_line == 'Free':
                            await conn.execute('''
                                UPDATE user_points
                                SET points = 0
                                WHERE user_id = $1
                            ''', submission['user_id'])
                            
                            if submission['tiktok_username']:
                                await conn.execute('''
                                    UPDATE tiktok_accounts
                                    SET points = 0
                                    WHERE handle_name = $1
                                ''', submission['tiktok_username'])
                        
                        return submission
                
                return None

    @app_commands.command(name="next", description="Play the next song in queue")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def next(self, interaction: discord.Interaction):
        await interaction.response.defer()
        
        submission = await self.get_next_submission()
        
        if not submission:
            await interaction.followup.send("❌ No songs in queue!")
            return
        
        embed = discord.Embed(
            title="🎵 Now Playing",
            color=discord.Color.green()
        )
        embed.add_field(name="Artist", value=submission['artist_name'], inline=True)
        embed.add_field(name="Song", value=submission['song_name'], inline=True)
        embed.add_field(name="Submitted by", value=submission['username'], inline=True)
        
        if submission['link_or_file']:
            embed.add_field(name="Link", value=submission['link_or_file'], inline=False)
        
        if submission['note']:
            embed.add_field(name="Note", value=submission['note'], inline=False)
        
        embed.add_field(name="Queue Line", value=submission['queue_line'], inline=True)
        embed.add_field(name="ID", value=submission['public_id'], inline=True)
        
        await interaction.followup.send(embed=embed)
        self.bot.dispatch('queue_update')

    @app_commands.command(name="queue", description="View the current queue")
    async def view_queue(self, interaction: discord.Interaction, page: int = 1):
        await interaction.response.defer(ephemeral=True)
        
        offset = (page - 1) * 10
        
        submissions = await db.fetch('''
            SELECT * FROM submissions
            WHERE played_time IS NULL AND queue_line NOT IN ('Removed', 'Songs Played')
            ORDER BY 
                CASE queue_line
                    WHEN '25+ Skip' THEN 1
                    WHEN '20 Skip' THEN 2
                    WHEN '15 Skip' THEN 3
                    WHEN '10 Skip' THEN 4
                    WHEN '5 Skip' THEN 5
                    WHEN 'Free' THEN 6
                    WHEN 'Pending Skips' THEN 7
                    ELSE 999
                END,
                CASE WHEN queue_line = 'Free' THEN total_score ELSE 0 END DESC,
                submission_time ASC
            LIMIT 10 OFFSET $1
        ''', offset)
        
        total = await db.fetchval('''
            SELECT COUNT(*) FROM submissions
            WHERE played_time IS NULL AND queue_line NOT IN ('Removed', 'Songs Played')
        ''')
        
        if not submissions:
            await interaction.followup.send("The queue is empty!", ephemeral=True)
            return
        
        embed = discord.Embed(
            title=f"📋 Queue (Page {page}/{(total + 9) // 10})",
            color=discord.Color.blue()
        )
        
        for i, sub in enumerate(submissions, start=offset + 1):
            value = f"**{sub['artist_name']}** - {sub['song_name']}\n"
            value += f"By: {sub['username']} | Queue: {sub['queue_line']}"
            if sub['total_score'] > 0:
                value += f" | Score: {sub['total_score']:.1f}"
            embed.add_field(
                name=f"{i}. ID: {sub['public_id']}",
                value=value,
                inline=False
            )
        
        embed.set_footer(text=f"Total songs in queue: {total}")
        await interaction.followup.send(embed=embed, ephemeral=True)

    @app_commands.command(name="remove-submission", description="Remove a submission from the queue")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def remove_submission(self, interaction: discord.Interaction, submission_id: str):
        await interaction.response.defer()
        
        result = await db.execute('''
            UPDATE submissions
            SET queue_line = 'Removed'
            WHERE public_id = $1 AND played_time IS NULL
        ''', submission_id)
        
        if result == "UPDATE 0":
            await interaction.followup.send(f"❌ Submission `{submission_id}` not found or already played.")
            return
        
        await interaction.followup.send(f"✅ Submission `{submission_id}` removed from queue.")
        self.bot.dispatch('queue_update')


async def setup(bot):
    await bot.add_cog(Queue(bot))
