import discord
from discord.ext import commands, tasks
from discord import app_commands
import logging
from database import db
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class LuxuryCoins(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.watch_time_tracker.start()

    def cog_unload(self):
        self.watch_time_tracker.cancel()

    @tasks.loop(minutes=1)
    async def watch_time_tracker(self):
        current_session = await db.fetchrow('''
            SELECT id FROM live_sessions
            WHERE end_time IS NULL
            ORDER BY start_time DESC
            LIMIT 1
        ''')
        
        if not current_session:
            return
        
        session_id = current_session['id']
        
        await db.execute('''
            UPDATE tiktok_watch_time
            SET watch_seconds = watch_seconds + 60,
                last_updated = NOW()
            WHERE session_id = $1
        ''', session_id)
        
        watch_records = await db.fetch('''
            SELECT tw.*, ta.linked_discord_id
            FROM tiktok_watch_time tw
            JOIN tiktok_accounts ta ON tw.tiktok_account_id = ta.handle_id
            WHERE tw.session_id = $1 AND ta.linked_discord_id IS NOT NULL
        ''', session_id)
        
        for record in watch_records:
            if record['watch_seconds'] >= 1800:
                coins_earned = record['watch_seconds'] // 1800
                
                await db.execute('''
                    INSERT INTO luxury_coins (user_id, balance)
                    VALUES ($1, $2)
                    ON CONFLICT (user_id) DO UPDATE
                    SET balance = luxury_coins.balance + $2
                ''', record['linked_discord_id'], coins_earned)
                
                await db.execute('''
                    UPDATE tiktok_watch_time
                    SET watch_seconds = watch_seconds % 1800
                    WHERE id = $1
                ''', record['id'])

    @watch_time_tracker.before_loop
    async def before_watch_time_tracker(self):
        await self.bot.wait_until_ready()

    async def award_coins_from_gifts(self, tiktok_account_id: int, coin_value: int):
        if coin_value >= 100:
            coins_earned = (coin_value // 100) * 2
            
            linked_discord_id = await db.fetchval(
                'SELECT linked_discord_id FROM tiktok_accounts WHERE handle_id = $1',
                tiktok_account_id
            )
            
            if linked_discord_id:
                await db.execute('''
                    INSERT INTO luxury_coins (user_id, balance)
                    VALUES ($1, $2)
                    ON CONFLICT (user_id) DO UPDATE
                    SET balance = luxury_coins.balance + $2
                ''', linked_discord_id, coins_earned)

    @app_commands.command(name="coins", description="Check your Luxury Coins balance")
    async def check_coins(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        
        balance = await db.fetchval(
            'SELECT balance FROM luxury_coins WHERE user_id = $1',
            interaction.user.id
        )
        
        if balance is None:
            balance = 0
        
        embed = discord.Embed(
            title="💰 Luxury Coins Balance",
            description=f"You have **{balance}** Luxury Coins",
            color=discord.Color.gold()
        )
        embed.add_field(
            name="How to Earn",
            value="• 1 coin per 30 minutes watch time\n• 2 coins per 100 gifted coins",
            inline=False
        )
        embed.add_field(
            name="Spend Coins",
            value="Use `/buy-skip` to move your submission to the 10 Skip queue (costs 1000 coins)",
            inline=False
        )
        
        await interaction.followup.send(embed=embed, ephemeral=True)

    @app_commands.command(name="buy-skip", description="Spend 1000 Luxury Coins to move your submission to 10 Skip tier")
    async def buy_skip(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        
        balance = await db.fetchval(
            'SELECT balance FROM luxury_coins WHERE user_id = $1',
            interaction.user.id
        )
        
        if balance is None or balance < 1000:
            await interaction.followup.send(
                f"❌ Insufficient Luxury Coins. You need 1000 coins (you have {balance or 0}).",
                ephemeral=True
            )
            return
        
        submission = await db.fetchrow('''
            SELECT * FROM submissions
            WHERE user_id = $1 AND queue_line IN ('Free', 'Pending Skips', '5 Skip')
            AND played_time IS NULL
            ORDER BY submission_time DESC
            LIMIT 1
        ''', interaction.user.id)
        
        if not submission:
            await interaction.followup.send(
                "❌ You don't have any eligible submissions to skip.",
                ephemeral=True
            )
            return
        
        async with db.pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(
                    'UPDATE luxury_coins SET balance = balance - 1000 WHERE user_id = $1',
                    interaction.user.id
                )
                
                await conn.execute(
                    'UPDATE submissions SET queue_line = $1 WHERE id = $2',
                    '10 Skip', submission['id']
                )
        
        await interaction.followup.send(
            f"✅ Successfully moved submission `{submission['public_id']}` to 10 Skip queue!\n"
            f"Remaining balance: {balance - 1000} Luxury Coins",
            ephemeral=True
        )
        
        self.bot.dispatch('queue_update')

    @app_commands.command(name="admin-give-coins", description="Admin: Give Luxury Coins to a user")
    @app_commands.checks.has_permissions(administrator=True)
    async def admin_give_coins(self, interaction: discord.Interaction, 
                              user: discord.Member, amount: int):
        await interaction.response.defer()
        
        await db.execute('''
            INSERT INTO luxury_coins (user_id, balance)
            VALUES ($1, $2)
            ON CONFLICT (user_id) DO UPDATE
            SET balance = luxury_coins.balance + $2
        ''', user.id, amount)
        
        new_balance = await db.fetchval(
            'SELECT balance FROM luxury_coins WHERE user_id = $1',
            user.id
        )
        
        await interaction.followup.send(
            f"✅ Gave {amount} Luxury Coins to {user.mention}. New balance: {new_balance}"
        )
        
        logger.info(f"Admin {interaction.user} gave {amount} coins to {user} ({user.id})")

    @app_commands.command(name="leaderboard-coins", description="View Luxury Coins leaderboard")
    async def leaderboard_coins(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        
        top_users = await db.fetch('''
            SELECT user_id, balance FROM luxury_coins
            ORDER BY balance DESC
            LIMIT 10
        ''')
        
        if not top_users:
            await interaction.followup.send(
                "No users have Luxury Coins yet.",
                ephemeral=True
            )
            return
        
        embed = discord.Embed(
            title="💰 Luxury Coins Leaderboard",
            color=discord.Color.gold()
        )
        
        for i, row in enumerate(top_users, 1):
            user = self.bot.get_user(row['user_id'])
            username = user.name if user else f"Unknown ({row['user_id']})"
            embed.add_field(
                name=f"{i}. {username}",
                value=f"{row['balance']} coins",
                inline=False
            )
        
        await interaction.followup.send(embed=embed, ephemeral=True)


async def setup(bot):
    await bot.add_cog(LuxuryCoins(bot))
