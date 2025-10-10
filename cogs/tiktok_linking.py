import discord
from discord.ext import commands
from discord import app_commands
import logging
from database import db
import os

logger = logging.getLogger(__name__)


class TikTokLinking(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def handle_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str,
    ) -> list[app_commands.Choice[str]]:
        if len(current) < 2:
            return []
        
        handles = await db.fetch('''
            SELECT handle_name FROM tiktok_accounts
            WHERE handle_name ILIKE $1
            ORDER BY last_seen DESC
            LIMIT 25
        ''', f'{current}%')
        
        return [
            app_commands.Choice(name=row['handle_name'], value=row['handle_name'])
            for row in handles
        ]

    @app_commands.command(name="link-tiktok", description="Link your TikTok handle to your Discord account")
    @app_commands.autocomplete(handle=handle_autocomplete)
    async def link_tiktok(self, interaction: discord.Interaction, handle: str):
        await interaction.response.defer(ephemeral=True)
        
        allow_any = os.getenv('ALLOW_ANY_HANDLE_LINKING', 'false').lower() == 'true'
        
        if not allow_any:
            exists = await db.fetchval(
                'SELECT 1 FROM tiktok_accounts WHERE handle_name = $1',
                handle
            )
            
            if not exists:
                await interaction.followup.send(
                    f"❌ Handle `@{handle}` not found. It must be seen in a live stream first.",
                    ephemeral=True
                )
                return
        
        existing = await db.fetchval(
            'SELECT 1 FROM tiktok_accounts WHERE handle_name = $1 AND linked_discord_id = $2',
            handle, interaction.user.id
        )
        
        if existing:
            await interaction.followup.send(
                f"✅ You're already linked to `@{handle}`",
                ephemeral=True
            )
            return
        
        if allow_any:
            await db.execute('''
                INSERT INTO tiktok_accounts (handle_name, linked_discord_id)
                VALUES ($1, $2)
                ON CONFLICT (handle_name) DO UPDATE
                SET linked_discord_id = $2
            ''', handle, interaction.user.id)
        else:
            await db.execute(
                'UPDATE tiktok_accounts SET linked_discord_id = $1 WHERE handle_name = $2',
                interaction.user.id, handle
            )
        
        await interaction.followup.send(
            f"✅ Successfully linked to TikTok handle `@{handle}`",
            ephemeral=True
        )

    @app_commands.command(name="unlink-tiktok", description="Unlink a TikTok handle from your account")
    @app_commands.autocomplete(handle=handle_autocomplete)
    async def unlink_tiktok(self, interaction: discord.Interaction, handle: str):
        await interaction.response.defer(ephemeral=True)
        
        result = await db.execute(
            'UPDATE tiktok_accounts SET linked_discord_id = NULL WHERE handle_name = $1 AND linked_discord_id = $2',
            handle, interaction.user.id
        )
        
        if result == "UPDATE 0":
            await interaction.followup.send(
                f"❌ You're not linked to `@{handle}`",
                ephemeral=True
            )
            return
        
        await interaction.followup.send(
            f"✅ Unlinked from TikTok handle `@{handle}`",
            ephemeral=True
        )

    @app_commands.command(name="admin-link", description="Admin: Force link a TikTok handle to a user")
    @app_commands.checks.has_permissions(administrator=True)
    async def admin_link(self, interaction: discord.Interaction, 
                        user: discord.Member, handle: str):
        await interaction.response.defer()
        
        await db.execute('''
            INSERT INTO tiktok_accounts (handle_name, linked_discord_id)
            VALUES ($1, $2)
            ON CONFLICT (handle_name) DO UPDATE
            SET linked_discord_id = $2
        ''', handle, user.id)
        
        await interaction.followup.send(
            f"✅ Force-linked `@{handle}` to {user.mention}"
        )
        
        logger.info(f"Admin {interaction.user} force-linked @{handle} to {user} ({user.id})")

    @app_commands.command(name="admin-unlink", description="Admin: Force unlink a TikTok handle from a user")
    @app_commands.checks.has_permissions(administrator=True)
    async def admin_unlink(self, interaction: discord.Interaction, 
                          user: discord.Member, handle: str):
        await interaction.response.defer()
        
        result = await db.execute(
            'UPDATE tiktok_accounts SET linked_discord_id = NULL WHERE handle_name = $1 AND linked_discord_id = $2',
            handle, user.id
        )
        
        if result == "UPDATE 0":
            await interaction.followup.send(
                f"❌ `@{handle}` is not linked to {user.mention}"
            )
            return
        
        await interaction.followup.send(
            f"✅ Force-unlinked `@{handle}` from {user.mention}"
        )
        
        logger.info(f"Admin {interaction.user} force-unlinked @{handle} from {user} ({user.id})")

    @app_commands.command(name="my-links", description="View your linked TikTok handles")
    async def my_links(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        
        handles = await db.fetch(
            'SELECT handle_name, points FROM tiktok_accounts WHERE linked_discord_id = $1',
            interaction.user.id
        )
        
        if not handles:
            await interaction.followup.send(
                "You don't have any linked TikTok handles.",
                ephemeral=True
            )
            return
        
        embed = discord.Embed(
            title="Your Linked TikTok Handles",
            color=discord.Color.blue()
        )
        
        for row in handles:
            embed.add_field(
                name=f"@{row['handle_name']}",
                value=f"Points: {row['points']}",
                inline=False
            )
        
        await interaction.followup.send(embed=embed, ephemeral=True)


async def setup(bot):
    await bot.add_cog(TikTokLinking(bot))
