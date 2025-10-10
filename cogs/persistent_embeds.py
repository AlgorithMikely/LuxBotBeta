import discord
from discord.ext import commands, tasks
from discord import app_commands
import logging
from database import db
import hashlib
import asyncio

logger = logging.getLogger(__name__)


class PersistentEmbeds(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.refresh_embeds.start()

    def cog_unload(self):
        self.refresh_embeds.cancel()

    @tasks.loop(seconds=10)
    async def refresh_embeds(self):
        embeds = await db.fetch(
            'SELECT * FROM persistent_embeds WHERE is_active = TRUE'
        )
        
        for i, embed_config in enumerate(embeds):
            if i > 0:
                await asyncio.sleep(1)
            
            try:
                await self.update_embed(embed_config)
            except Exception as e:
                logger.error(f"Error updating embed {embed_config['id']}: {e}")

    @refresh_embeds.before_loop
    async def before_refresh_embeds(self):
        await self.bot.wait_until_ready()

    async def update_embed(self, embed_config):
        channel = self.bot.get_channel(embed_config['channel_id'])
        if not channel:
            return
        
        if embed_config['embed_type'] == 'live_queue':
            content = await self.generate_live_queue_embed(embed_config['current_page'])
        elif embed_config['embed_type'] == 'reviewer_main':
            content = await self.generate_reviewer_main_embed(embed_config['current_page'])
        elif embed_config['embed_type'] == 'reviewer_pending':
            content = await self.generate_reviewer_pending_embed(embed_config['current_page'])
        else:
            return
        
        content_hash = hashlib.md5(str(content).encode()).hexdigest()
        
        if content_hash == embed_config['last_content_hash']:
            return
        
        try:
            message = await channel.fetch_message(embed_config['message_id'])
            
            if embed_config['embed_type'] in ['reviewer_main', 'reviewer_pending']:
                view = ReviewerView(self.bot, embed_config['embed_type'])
                await message.edit(embed=content, view=view)
            else:
                await message.edit(embed=content)
            
            await db.execute('''
                UPDATE persistent_embeds
                SET last_content_hash = $1, last_updated = NOW()
                WHERE id = $2
            ''', content_hash, embed_config['id'])
            
        except discord.NotFound:
            await self.recreate_embed(embed_config)

    async def recreate_embed(self, embed_config):
        channel = self.bot.get_channel(embed_config['channel_id'])
        if not channel:
            return
        
        if embed_config['embed_type'] == 'live_queue':
            embed = await self.generate_live_queue_embed(0)
            message = await channel.send(embed=embed)
        elif embed_config['embed_type'] in ['reviewer_main', 'reviewer_pending']:
            embed = await self.generate_reviewer_main_embed(0) if embed_config['embed_type'] == 'reviewer_main' else await self.generate_reviewer_pending_embed(0)
            view = ReviewerView(self.bot, embed_config['embed_type'])
            message = await channel.send(embed=embed, view=view)
        
        await db.execute('''
            UPDATE persistent_embeds
            SET message_id = $1, current_page = 0
            WHERE id = $2
        ''', message.id, embed_config['id'])

    async def generate_live_queue_embed(self, page: int = 0):
        offset = page * 10
        
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
        
        embed = discord.Embed(
            title=f"🎵 Live Queue (Page {page + 1}/{max((total + 9) // 10, 1)})",
            color=discord.Color.blue()
        )
        
        if not submissions:
            embed.description = "No songs in queue"
        else:
            for i, sub in enumerate(submissions, start=offset + 1):
                emoji = self.get_queue_emoji(sub['queue_line'])
                value = f"{emoji} **{sub['artist_name']}** - {sub['song_name']}\n"
                value += f"By: {sub['username']}"
                if sub['total_score'] > 0:
                    value += f" | Score: {sub['total_score']:.1f}"
                embed.add_field(
                    name=f"{i}. {sub['queue_line']}",
                    value=value,
                    inline=False
                )
        
        embed.set_footer(text=f"Total: {total} songs | Updates every 10s")
        return embed

    async def generate_reviewer_main_embed(self, page: int = 0):
        offset = page * 5
        
        submissions = await db.fetch('''
            SELECT * FROM submissions
            WHERE played_time IS NULL AND queue_line NOT IN ('Removed', 'Songs Played', 'Pending Skips')
            ORDER BY 
                CASE queue_line
                    WHEN '25+ Skip' THEN 1
                    WHEN '20 Skip' THEN 2
                    WHEN '15 Skip' THEN 3
                    WHEN '10 Skip' THEN 4
                    WHEN '5 Skip' THEN 5
                    WHEN 'Free' THEN 6
                    ELSE 999
                END,
                submission_time ASC
            LIMIT 5 OFFSET $1
        ''', offset)
        
        total = await db.fetchval('''
            SELECT COUNT(*) FROM submissions
            WHERE played_time IS NULL AND queue_line NOT IN ('Removed', 'Songs Played', 'Pending Skips')
        ''')
        
        embed = discord.Embed(
            title=f"📋 Reviewer Queue (Page {page + 1}/{max((total + 4) // 5, 1)})",
            color=discord.Color.green()
        )
        
        if not submissions:
            embed.description = "No submissions to review"
        else:
            for sub in submissions:
                value = f"**Artist:** {sub['artist_name']}\n"
                value += f"**Song:** {sub['song_name']}\n"
                value += f"**By:** {sub['username']}\n"
                value += f"**Queue:** {sub['queue_line']}\n"
                if sub['link_or_file']:
                    value += f"**Link:** {sub['link_or_file'][:50]}...\n" if len(sub['link_or_file']) > 50 else f"**Link:** {sub['link_or_file']}\n"
                if sub['note']:
                    value += f"**Note:** {sub['note']}\n"
                embed.add_field(
                    name=f"ID: {sub['public_id']}",
                    value=value,
                    inline=False
                )
        
        embed.set_footer(text=f"Total: {total} submissions")
        return embed

    async def generate_reviewer_pending_embed(self, page: int = 0):
        offset = page * 5
        
        submissions = await db.fetch('''
            SELECT * FROM submissions
            WHERE played_time IS NULL AND queue_line = 'Pending Skips'
            ORDER BY submission_time ASC
            LIMIT 5 OFFSET $1
        ''', offset)
        
        total = await db.fetchval('''
            SELECT COUNT(*) FROM submissions
            WHERE played_time IS NULL AND queue_line = 'Pending Skips'
        ''')
        
        embed = discord.Embed(
            title=f"⏳ Pending Skips (Page {page + 1}/{max((total + 4) // 5, 1)})",
            color=discord.Color.orange()
        )
        
        if not submissions:
            embed.description = "No pending skip submissions"
        else:
            for sub in submissions:
                value = f"**Artist:** {sub['artist_name']}\n"
                value += f"**Song:** {sub['song_name']}\n"
                value += f"**By:** {sub['username']}\n"
                if sub['link_or_file']:
                    value += f"**Link:** {sub['link_or_file'][:50]}...\n" if len(sub['link_or_file']) > 50 else f"**Link:** {sub['link_or_file']}\n"
                embed.add_field(
                    name=f"ID: {sub['public_id']}",
                    value=value,
                    inline=False
                )
        
        embed.set_footer(text=f"Total: {total} pending")
        return embed

    def get_queue_emoji(self, queue_line: str):
        emojis = {
            '25+ Skip': '🏆',
            '20 Skip': '💎',
            '15 Skip': '⭐',
            '10 Skip': '🎯',
            '5 Skip': '🎪',
            'Free': '🎵',
            'Pending Skips': '⏳'
        }
        return emojis.get(queue_line, '📝')

    @commands.Cog.listener()
    async def on_queue_update(self):
        pass


class ReviewerView(discord.ui.View):
    def __init__(self, bot, embed_type):
        super().__init__(timeout=None)
        self.bot = bot
        self.embed_type = embed_type

    @discord.ui.button(label="Approve", style=discord.ButtonStyle.green, custom_id="approve_submission")
    async def approve_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(ApproveModal(self.bot))

    @discord.ui.button(label="Remove", style=discord.ButtonStyle.red, custom_id="remove_submission")
    async def remove_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(RemoveModal(self.bot))


class ApproveModal(discord.ui.Modal, title="Approve Submission"):
    submission_id = discord.ui.TextInput(
        label="Submission ID",
        placeholder="Enter the submission ID to approve",
        required=True
    )

    def __init__(self, bot):
        super().__init__()
        self.bot = bot

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        
        submission = await db.fetchrow(
            'SELECT * FROM submissions WHERE public_id = $1 AND queue_line = $2',
            self.submission_id.value, 'Pending Skips'
        )
        
        if not submission:
            await interaction.followup.send(
                f"❌ Submission `{self.submission_id.value}` not found in Pending Skips.",
                ephemeral=True
            )
            return
        
        await db.execute(
            'UPDATE submissions SET queue_line = $1 WHERE public_id = $2',
            'Free', self.submission_id.value
        )
        
        await interaction.followup.send(
            f"✅ Approved submission `{self.submission_id.value}`",
            ephemeral=True
        )
        
        self.bot.dispatch('queue_update')


class RemoveModal(discord.ui.Modal, title="Remove Submission"):
    submission_id = discord.ui.TextInput(
        label="Submission ID",
        placeholder="Enter the submission ID to remove",
        required=True
    )

    def __init__(self, bot):
        super().__init__()
        self.bot = bot

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        
        result = await db.execute(
            'UPDATE submissions SET queue_line = $1 WHERE public_id = $2 AND played_time IS NULL',
            'Removed', self.submission_id.value
        )
        
        if result == "UPDATE 0":
            await interaction.followup.send(
                f"❌ Submission `{self.submission_id.value}` not found.",
                ephemeral=True
            )
            return
        
        await interaction.followup.send(
            f"✅ Removed submission `{self.submission_id.value}`",
            ephemeral=True
        )
        
        self.bot.dispatch('queue_update')


async def setup(bot):
    await bot.add_cog(PersistentEmbeds(bot))
