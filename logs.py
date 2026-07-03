import json
import os
from datetime import datetime, timezone

import discord
from discord.ext import commands

CONFIG_PATH = "data/config.json"


def ensure_config_file():
    os.makedirs("data", exist_ok=True)
    if not os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump({}, f, indent=4)


def load_config():
    ensure_config_file()
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def save_config(data):
    ensure_config_file()
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)


def get_guild_config(guild_id: int):
    config = load_config()
    return config.get(str(guild_id), {})


def update_guild_config(guild_id: int, new_data: dict):
    config = load_config()
    guild_id = str(guild_id)

    if guild_id not in config:
        config[guild_id] = {}

    config[guild_id].update(new_data)
    save_config(config)


class Logs(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.timeout_cache = {}

    def make_embed(self, title: str, color: discord.Color, description: str = None):
        return discord.Embed(
            title=title,
            description=description,
            color=color,
            timestamp=datetime.now(timezone.utc)
        )

    def user_string(self, user):
        return f"{user.mention} (`{user.id}`)"

    def role_list(self, member: discord.Member):
        roles = [role.mention for role in member.roles if role.name != "@everyone"]
        return ", ".join(roles[:20]) if roles else "Aucun role"

    async def send_log(self, guild: discord.Guild, log_type: str, embed: discord.Embed):
        guild_config = get_guild_config(guild.id)
        channel_id = guild_config.get(log_type)

        if not channel_id:
            return

        channel = guild.get_channel(channel_id)

        if channel is None:
            try:
                channel = await self.bot.fetch_channel(channel_id)
            except Exception:
                return

        if not isinstance(channel, discord.TextChannel):
            return

        try:
            await channel.send(embed=embed)
        except Exception:
            pass

    async def get_audit_entry(self, guild: discord.Guild, action: discord.AuditLogAction, target_id: int = None, limit: int = 8):
        me = guild.me or guild.get_member(self.bot.user.id)
        if not me or not me.guild_permissions.view_audit_log:
            return None

        try:
            async for entry in guild.audit_logs(limit=limit, action=action):
                if target_id is None:
                    return entry

                target = entry.target
                if target and getattr(target, "id", None) == target_id:
                    return entry
        except Exception:
            return None

        return None

    @commands.command(name="autologs")
    @commands.has_permissions(administrator=True)
    @commands.guild_only()
    async def autologs(self, ctx):
        guild = ctx.guild
        guild_config = get_guild_config(guild.id)

        existing_category = discord.utils.get(guild.categories, name="Logs")

        if existing_category is None:
            overwrites = {
                guild.default_role: discord.PermissionOverwrite(view_channel=False)
            }

            me = guild.me or guild.get_member(self.bot.user.id)
            if me is not None:
                overwrites[me] = discord.PermissionOverwrite(
                    view_channel=True,
                    send_messages=True,
                    embed_links=True,
                    read_message_history=True,
                    manage_channels=True
                )

            for role in guild.roles:
                if role.permissions.administrator:
                    overwrites[role] = discord.PermissionOverwrite(view_channel=True)

            category = await guild.create_category("Logs", overwrites=overwrites)
        else:
            category = existing_category

        channels_map = {
            "general_logs": "logs-generaux",
            "message_logs": "logs-messages",
            "member_logs": "logs-membres",
            "mod_logs": "logs-moderation",
            "voice_logs": "logs-vocaux",
            "role_logs": "logs-roles"
        }

        created_channels = []
        reused_channels = []
        saved_data = {}

        for key, default_name in channels_map.items():
            channel = None

            saved_channel_id = guild_config.get(key)
            if saved_channel_id:
                channel = guild.get_channel(saved_channel_id)
                if channel is None:
                    try:
                        fetched = await self.bot.fetch_channel(saved_channel_id)
                        if isinstance(fetched, discord.TextChannel):
                            channel = fetched
                    except Exception:
                        channel = None

            if channel is None:
                channel = discord.utils.get(guild.text_channels, name=default_name)

            if channel is None:
                channel = await guild.create_text_channel(
                    name=default_name,
                    category=category
                )
                created_channels.append(channel.mention)
            else:
                if channel.category != category:
                    try:
                        await channel.edit(category=category)
                    except Exception:
                        pass
                reused_channels.append(channel.mention)

            saved_data[key] = channel.id

        update_guild_config(guild.id, saved_data)

        embed = self.make_embed(
            title="Configuration automatique terminee",
            description="Les salons de logs ont ete configures avec succes.",
            color=discord.Color.green()
        )

        if created_channels:
            embed.add_field(
                name="Salons crees",
                value="\n".join(created_channels),
                inline=False
            )

        if reused_channels:
            embed.add_field(
                name="Salons reutilises",
                value="\n".join(reused_channels),
                inline=False
            )

        embed.add_field(name="Categorie", value=category.name, inline=False)
        embed.set_footer(text=f"Serveur: {guild.name}")

        await ctx.send(embed=embed)

    @commands.command(name="configlogs")
    @commands.has_permissions(administrator=True)
    @commands.guild_only()
    async def configlogs(self, ctx):
        guild_config = get_guild_config(ctx.guild.id)

        if not guild_config:
            embed = self.make_embed(
                title="Aucune configuration",
                description="Utilise `+autologs` pour creer automatiquement les salons.",
                color=discord.Color.orange()
            )
            await ctx.send(embed=embed)
            return

        labels = {
            "general_logs": "Logs generaux",
            "message_logs": "Logs messages",
            "member_logs": "Logs membres",
            "mod_logs": "Logs moderation",
            "voice_logs": "Logs vocaux",
            "role_logs": "Logs roles",
            "prefix": "Prefixe"
        }

        lines = []

        for key, label in labels.items():
            if key == "prefix":
                lines.append(f"**{label}** : `{guild_config.get('prefix', '+')}`")
                continue

            channel_id = guild_config.get(key)
            if not channel_id:
                lines.append(f"**{label}** : Non configure")
                continue

            channel = ctx.guild.get_channel(channel_id)
            if channel:
                lines.append(f"**{label}** : {channel.mention}")
            else:
                lines.append(f"**{label}** : Salon introuvable (`{channel_id}`)")

        embed = self.make_embed(
            title="Configuration des logs",
            description="\n".join(lines),
            color=discord.Color.blurple()
        )

        await ctx.send(embed=embed)

    @commands.command(name="logtest")
    @commands.has_permissions(administrator=True)
    @commands.guild_only()
    async def logtest(self, ctx):
        embed = self.make_embed(
            title="Test des logs",
            description="Si tu vois ce message, les logs fonctionnent.",
            color=discord.Color.blurple()
        )
        embed.add_field(name="Serveur", value=ctx.guild.name, inline=True)
        embed.add_field(name="Declenche par", value=ctx.author.mention, inline=True)
        embed.set_thumbnail(url=ctx.author.display_avatar.url)

        await self.send_log(ctx.guild, "general_logs", embed)
        await ctx.send("Message de test envoye dans le salon de logs general.")

    @commands.command(name="setprefix")
    @commands.has_permissions(administrator=True)
    @commands.guild_only()
    async def setprefix(self, ctx, new_prefix: str):
        if len(new_prefix) > 5:
            await ctx.send("Le prefixe est trop long. Maximum 5 caracteres.")
            return

        update_guild_config(ctx.guild.id, {"prefix": new_prefix})

        embed = self.make_embed(
            title="Prefixe mis a jour",
            description=f"Le nouveau prefixe est `{new_prefix}`",
            color=discord.Color.green()
        )
        await ctx.send(embed=embed)

    @autologs.error
    @configlogs.error
    @logtest.error
    @setprefix.error
    async def admin_command_error(self, ctx, error):
        if isinstance(error, commands.MissingPermissions):
            await ctx.send("Tu dois etre administrateur pour utiliser cette commande.")
        elif isinstance(error, commands.NoPrivateMessage):
            await ctx.send("Cette commande doit etre utilisee dans un serveur.")
        elif isinstance(error, commands.MissingRequiredArgument):
            await ctx.send("Il manque un argument a la commande.")
        else:
            await ctx.send(f"Une erreur est survenue : `{error}`")

    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message):
        if not message.guild or message.author.bot:
            return

        content = message.content if message.content else "*Aucun contenu ou message non en cache.*"

        embed = self.make_embed(
            title="Message supprime",
            description=content[:4000],
            color=discord.Color.red()
        )
        embed.add_field(name="Auteur", value=self.user_string(message.author), inline=False)
        embed.add_field(name="Salon", value=message.channel.mention, inline=False)

        if message.attachments:
            attachments_value = "\n".join(att.url for att in message.attachments[:5])
            embed.add_field(name="Pieces jointes", value=attachments_value, inline=False)

        embed.set_thumbnail(url=message.author.display_avatar.url)
        embed.set_footer(text=f"Message ID: {message.id}")

        await self.send_log(message.guild, "message_logs", embed)

    @commands.Cog.listener()
    async def on_bulk_message_delete(self, messages):
        if not messages:
            return

        first_message = messages[0]
        if not first_message.guild:
            return

        human_messages = [m for m in messages if not m.author.bot]
        if not human_messages:
            return

        authors = {}
        for msg in human_messages[:20]:
            authors[str(msg.author)] = authors.get(str(msg.author), 0) + 1

        authors_text = "\n".join([f"{name} : {count}" for name, count in authors.items()]) or "Inconnu"

        embed = self.make_embed(
            title="Suppression multiple de messages",
            description=f"{len(human_messages)} messages ont ete supprimes.",
            color=discord.Color.dark_red()
        )
        embed.add_field(name="Salon", value=first_message.channel.mention, inline=False)
        embed.add_field(name="Auteurs", value=authors_text[:1024], inline=False)

        await self.send_log(first_message.guild, "message_logs", embed)

    @commands.Cog.listener()
    async def on_message_edit(self, before: discord.Message, after: discord.Message):
        if not before.guild or before.author.bot:
            return

        if before.content == after.content:
            return

        before_content = before.content if before.content else "*Vide*"
        after_content = after.content if after.content else "*Vide*"

        embed = self.make_embed(
            title="Message modifie",
            color=discord.Color.orange()
        )
        embed.add_field(name="Auteur", value=self.user_string(before.author), inline=False)
        embed.add_field(name="Salon", value=before.channel.mention, inline=False)
        embed.add_field(name="Avant", value=before_content[:1024], inline=False)
        embed.add_field(name="Apres", value=after_content[:1024], inline=False)
        embed.set_thumbnail(url=before.author.display_avatar.url)
        embed.set_footer(text=f"Message ID: {before.id}")

        await self.send_log(before.guild, "message_logs", embed)

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        embed = self.make_embed(
            title="Membre arrive",
            description=f"{member.mention} a rejoint le serveur.",
            color=discord.Color.green()
        )
        embed.add_field(name="Utilisateur", value=self.user_string(member), inline=False)
        embed.add_field(
            name="Compte cree le",
            value=discord.utils.format_dt(member.created_at, style="F"),
            inline=False
        )
        embed.add_field(name="Roles", value=self.role_list(member), inline=False)
        embed.set_thumbnail(url=member.display_avatar.url)

        await self.send_log(member.guild, "member_logs", embed)

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        audit_entry = await self.get_audit_entry(
            member.guild,
            discord.AuditLogAction.kick,
            member.id
        )

        if audit_entry:
            embed = self.make_embed(
                title="Membre kick",
                description=f"{member.mention} a ete expulse du serveur.",
                color=discord.Color.dark_orange()
            )
            embed.add_field(name="Utilisateur", value=self.user_string(member), inline=False)
            embed.add_field(
                name="Par",
                value=audit_entry.user.mention if audit_entry.user else "Inconnu",
                inline=False
            )
            embed.add_field(
                name="Raison",
                value=audit_entry.reason if audit_entry.reason else "Aucune raison",
                inline=False
            )
            embed.set_thumbnail(url=member.display_avatar.url)

            await self.send_log(member.guild, "mod_logs", embed)
            return

        embed = self.make_embed(
            title="Membre parti",
            description=f"{member.mention} a quitte le serveur.",
            color=discord.Color.dark_grey()
        )
        embed.add_field(name="Utilisateur", value=self.user_string(member), inline=False)
        embed.set_thumbnail(url=member.display_avatar.url)

        await self.send_log(member.guild, "member_logs", embed)

    @commands.Cog.listener()
    async def on_member_ban(self, guild: discord.Guild, user: discord.User):
        entry = await self.get_audit_entry(guild, discord.AuditLogAction.ban, user.id)

        embed = self.make_embed(
            title="Membre banni",
            description=f"{user.mention} a ete banni.",
            color=discord.Color.dark_red()
        )
        embed.add_field(name="Utilisateur", value=self.user_string(user), inline=False)
        embed.add_field(
            name="Par",
            value=entry.user.mention if entry and entry.user else "Inconnu",
            inline=False
        )
        embed.add_field(
            name="Raison",
            value=entry.reason if entry and entry.reason else "Aucune raison",
            inline=False
        )
        embed.set_thumbnail(url=user.display_avatar.url)

        await self.send_log(guild, "mod_logs", embed)

    @commands.Cog.listener()
    async def on_member_unban(self, guild: discord.Guild, user: discord.User):
        entry = await self.get_audit_entry(guild, discord.AuditLogAction.unban, user.id)

        embed = self.make_embed(
            title="Membre debanni",
            description=f"{user.mention} a ete debanni.",
            color=discord.Color.green()
        )
        embed.add_field(name="Utilisateur", value=self.user_string(user), inline=False)
        embed.add_field(
            name="Par",
            value=entry.user.mention if entry and entry.user else "Inconnu",
            inline=False
        )
        embed.add_field(
            name="Raison",
            value=entry.reason if entry and entry.reason else "Aucune raison",
            inline=False
        )
        embed.set_thumbnail(url=user.display_avatar.url)

        await self.send_log(guild, "mod_logs", embed)

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        if before.nick != after.nick:
            embed = self.make_embed(
                title="Pseudo modifie",
                description=f"Le pseudo de {after.mention} a ete modifie.",
                color=discord.Color.blurple()
            )
            embed.add_field(name="Utilisateur", value=self.user_string(after), inline=False)
            embed.add_field(name="Avant", value=before.nick if before.nick else before.name, inline=False)
            embed.add_field(name="Apres", value=after.nick if after.nick else after.name, inline=False)
            embed.set_thumbnail(url=after.display_avatar.url)

            await self.send_log(after.guild, "member_logs", embed)

        if before.display_name != after.display_name and before.nick == after.nick:
            embed = self.make_embed(
                title="Nom d'affichage modifie",
                description=f"Le nom d'affichage de {after.mention} a change.",
                color=discord.Color.blurple()
            )
            embed.add_field(name="Utilisateur", value=self.user_string(after), inline=False)
            embed.add_field(name="Avant", value=before.display_name, inline=False)
            embed.add_field(name="Apres", value=after.display_name, inline=False)
            embed.set_thumbnail(url=after.display_avatar.url)

            await self.send_log(after.guild, "member_logs", embed)

        before_roles = set(before.roles)
        after_roles = set(after.roles)

        added_roles = after_roles - before_roles
        removed_roles = before_roles - after_roles

        if added_roles or removed_roles:
            entry = await self.get_audit_entry(
                after.guild,
                discord.AuditLogAction.member_role_update,
                after.id
            )

            actor = entry.user.mention if entry and entry.user else "Inconnu"
            reason = entry.reason if entry and entry.reason else "Aucune raison"

            for role in added_roles:
                if role.name == "@everyone":
                    continue

                embed = self.make_embed(
                    title="Role ajoute",
                    description=f"Un role a ete ajoute a {after.mention}.",
                    color=discord.Color.green()
                )
                embed.add_field(name="Utilisateur", value=self.user_string(after), inline=False)
                embed.add_field(name="Role ajoute", value=role.mention, inline=False)
                embed.add_field(name="Ajoute par", value=actor, inline=False)
                embed.add_field(name="Raison", value=reason, inline=False)
                embed.add_field(name="Roles actuels", value=self.role_list(after), inline=False)
                embed.set_thumbnail(url=after.display_avatar.url)

                await self.send_log(after.guild, "role_logs", embed)

            for role in removed_roles:
                if role.name == "@everyone":
                    continue

                embed = self.make_embed(
                    title="Role retire",
                    description=f"Un role a ete retire a {after.mention}.",
                    color=discord.Color.orange()
                )
                embed.add_field(name="Utilisateur", value=self.user_string(after), inline=False)
                embed.add_field(name="Role retire", value=role.mention, inline=False)
                embed.add_field(name="Retire par", value=actor, inline=False)
                embed.add_field(name="Raison", value=reason, inline=False)
                embed.add_field(name="Roles actuels", value=self.role_list(after), inline=False)
                embed.set_thumbnail(url=after.display_avatar.url)

                await self.send_log(after.guild, "role_logs", embed)

        before_timeout = before.timed_out_until
        after_timeout = after.timed_out_until

        if before_timeout != after_timeout:
            entry = await self.get_audit_entry(
                after.guild,
                discord.AuditLogAction.member_update,
                after.id
            )

            actor = entry.user.mention if entry and entry.user else "Inconnu"
            reason = entry.reason if entry and entry.reason else "Aucune raison"

            if before_timeout is None and after_timeout is not None:
                embed = self.make_embed(
                    title="Membre timeout",
                    description=f"{after.mention} a recu un timeout.",
                    color=discord.Color.dark_orange()
                )
                embed.add_field(name="Utilisateur", value=self.user_string(after), inline=False)
                embed.add_field(name="Par", value=actor, inline=False)
                embed.add_field(name="Jusqu'au", value=discord.utils.format_dt(after_timeout, style="F"), inline=False)
                embed.add_field(name="Raison", value=reason, inline=False)
                embed.set_thumbnail(url=after.display_avatar.url)

                await self.send_log(after.guild, "mod_logs", embed)

            elif before_timeout is not None and after_timeout is None:
                embed = self.make_embed(
                    title="Timeout retire",
                    description=f"Le timeout de {after.mention} a ete retire.",
                    color=discord.Color.green()
                )
                embed.add_field(name="Utilisateur", value=self.user_string(after), inline=False)
                embed.add_field(name="Par", value=actor, inline=False)
                embed.add_field(name="Raison", value=reason, inline=False)
                embed.set_thumbnail(url=after.display_avatar.url)

                await self.send_log(after.guild, "mod_logs", embed)

            elif before_timeout is not None and after_timeout is not None:
                embed = self.make_embed(
                    title="Timeout modifie",
                    description=f"Le timeout de {after.mention} a ete modifie.",
                    color=discord.Color.orange()
                )
                embed.add_field(name="Utilisateur", value=self.user_string(after), inline=False)
                embed.add_field(name="Par", value=actor, inline=False)
                embed.add_field(
                    name="Avant",
                    value=discord.utils.format_dt(before_timeout, style="F"),
                    inline=False
                )
                embed.add_field(
                    name="Apres",
                    value=discord.utils.format_dt(after_timeout, style="F"),
                    inline=False
                )
                embed.add_field(name="Raison", value=reason, inline=False)
                embed.set_thumbnail(url=after.display_avatar.url)

                await self.send_log(after.guild, "mod_logs", embed)

    @commands.Cog.listener()
    async def on_guild_role_create(self, role: discord.Role):
        entry = await self.get_audit_entry(role.guild, discord.AuditLogAction.role_create, role.id)

        embed = self.make_embed(
            title="Role cree",
            description=f"Le role {role.mention} a ete cree.",
            color=discord.Color.green()
        )
        embed.add_field(name="Nom", value=role.name, inline=True)
        embed.add_field(name="ID", value=str(role.id), inline=True)
        embed.add_field(name="Couleur", value=str(role.color), inline=True)
        embed.add_field(
            name="Cree par",
            value=entry.user.mention if entry and entry.user else "Inconnu",
            inline=False
        )
        embed.add_field(
            name="Raison",
            value=entry.reason if entry and entry.reason else "Aucune raison",
            inline=False
        )

        await self.send_log(role.guild, "role_logs", embed)

    @commands.Cog.listener()
    async def on_guild_role_delete(self, role: discord.Role):
        entry = await self.get_audit_entry(role.guild, discord.AuditLogAction.role_delete, role.id)

        embed = self.make_embed(
            title="Role supprime",
            description=f"Le role `{role.name}` a ete supprime.",
            color=discord.Color.red()
        )
        embed.add_field(name="Nom", value=role.name, inline=True)
        embed.add_field(name="ID", value=str(role.id), inline=True)
        embed.add_field(name="Couleur", value=str(role.color), inline=True)
        embed.add_field(
            name="Supprime par",
            value=entry.user.mention if entry and entry.user else "Inconnu",
            inline=False
        )
        embed.add_field(
            name="Raison",
            value=entry.reason if entry and entry.reason else "Aucune raison",
            inline=False
        )

        await self.send_log(role.guild, "role_logs", embed)

    @commands.Cog.listener()
    async def on_guild_role_update(self, before: discord.Role, after: discord.Role):
        changes = []

        if before.name != after.name:
            changes.append(f"**Nom** : `{before.name}` -> `{after.name}`")

        if before.color != after.color:
            changes.append(f"**Couleur** : `{before.color}` -> `{after.color}`")

        if before.hoist != after.hoist:
            changes.append(f"**Affiche separement** : `{before.hoist}` -> `{after.hoist}`")

        if before.mentionable != after.mentionable:
            changes.append(f"**Mentionnable** : `{before.mentionable}` -> `{after.mentionable}`")

        if not changes:
            return

        entry = await self.get_audit_entry(after.guild, discord.AuditLogAction.role_update, after.id)

        embed = self.make_embed(
            title="Role modifie",
            description=f"Le role {after.mention} a ete modifie.",
            color=discord.Color.blurple()
        )
        embed.add_field(name="Role", value=after.mention, inline=False)
        embed.add_field(name="Modifications", value="\n".join(changes)[:1024], inline=False)
        embed.add_field(
            name="Modifie par",
            value=entry.user.mention if entry and entry.user else "Inconnu",
            inline=False
        )
        embed.add_field(
            name="Raison",
            value=entry.reason if entry and entry.reason else "Aucune raison",
            inline=False
        )

        await self.send_log(after.guild, "role_logs", embed)

    @commands.Cog.listener()
    async def on_guild_channel_create(self, channel: discord.abc.GuildChannel):
        entry = await self.get_audit_entry(channel.guild, discord.AuditLogAction.channel_create, channel.id)

        embed = self.make_embed(
            title="Salon cree",
            description=f"Le salon `{channel.name}` a ete cree.",
            color=discord.Color.green()
        )
        embed.add_field(name="Type", value=str(channel.type), inline=True)
        embed.add_field(name="ID", value=str(channel.id), inline=True)
        embed.add_field(
            name="Cree par",
            value=entry.user.mention if entry and entry.user else "Inconnu",
            inline=False
        )
        embed.add_field(
            name="Raison",
            value=entry.reason if entry and entry.reason else "Aucune raison",
            inline=False
        )

        await self.send_log(channel.guild, "general_logs", embed)

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel: discord.abc.GuildChannel):
        entry = await self.get_audit_entry(channel.guild, discord.AuditLogAction.channel_delete, channel.id)

        embed = self.make_embed(
            title="Salon supprime",
            description=f"Le salon `{channel.name}` a ete supprime.",
            color=discord.Color.red()
        )
        embed.add_field(name="Type", value=str(channel.type), inline=True)
        embed.add_field(name="ID", value=str(channel.id), inline=True)
        embed.add_field(
            name="Supprime par",
            value=entry.user.mention if entry and entry.user else "Inconnu",
            inline=False
        )
        embed.add_field(
            name="Raison",
            value=entry.reason if entry and entry.reason else "Aucune raison",
            inline=False
        )

        await self.send_log(channel.guild, "general_logs", embed)

    @commands.Cog.listener()
    async def on_guild_channel_update(self, before: discord.abc.GuildChannel, after: discord.abc.GuildChannel):
        changes = []

        if before.name != after.name:
            changes.append(f"**Nom** : `{before.name}` -> `{after.name}`")

        before_category = before.category.name if before.category else "Aucune"
        after_category = after.category.name if after.category else "Aucune"
        if before_category != after_category:
            changes.append(f"**Categorie** : `{before_category}` -> `{after_category}`")

        if not changes:
            return

        entry = await self.get_audit_entry(after.guild, discord.AuditLogAction.channel_update, after.id)

        embed = self.make_embed(
            title="Salon modifie",
            description=f"Le salon `{after.name}` a ete modifie.",
            color=discord.Color.blurple()
        )
        embed.add_field(name="Salon", value=after.mention if hasattr(after, "mention") else after.name, inline=False)
        embed.add_field(name="Modifications", value="\n".join(changes)[:1024], inline=False)
        embed.add_field(
            name="Modifie par",
            value=entry.user.mention if entry and entry.user else "Inconnu",
            inline=False
        )
        embed.add_field(
            name="Raison",
            value=entry.reason if entry and entry.reason else "Aucune raison",
            inline=False
        )

        await self.send_log(after.guild, "general_logs", embed)

    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        if before.channel != after.channel:
            embed = self.make_embed(
                title="Activite vocale",
                color=discord.Color.purple()
            )
            embed.add_field(name="Membre", value=self.user_string(member), inline=False)

            if before.channel is None and after.channel is not None:
                embed.description = f"{member.mention} a rejoint un salon vocal."
                embed.add_field(name="Salon", value=after.channel.name, inline=False)

            elif before.channel is not None and after.channel is None:
                embed.description = f"{member.mention} a quitte un salon vocal."
                embed.add_field(name="Salon", value=before.channel.name, inline=False)

            else:
                embed.description = f"{member.mention} a change de salon vocal."
                embed.add_field(name="Avant", value=before.channel.name, inline=True)
                embed.add_field(name="Apres", value=after.channel.name, inline=True)

            embed.set_thumbnail(url=member.display_avatar.url)
            await self.send_log(member.guild, "voice_logs", embed)

        if before.self_mute != after.self_mute:
            embed = self.make_embed(
                title="Mute micro",
                description=f"Changement de micro pour {member.mention}.",
                color=discord.Color.orange()
            )
            embed.add_field(name="Membre", value=self.user_string(member), inline=False)
            embed.add_field(name="Avant", value=str(before.self_mute), inline=True)
            embed.add_field(name="Apres", value=str(after.self_mute), inline=True)

            await self.send_log(member.guild, "voice_logs", embed)

        if before.self_deaf != after.self_deaf:
            embed = self.make_embed(
                title="Casque mute",
                description=f"Changement de casque pour {member.mention}.",
                color=discord.Color.orange()
            )
            embed.add_field(name="Membre", value=self.user_string(member), inline=False)
            embed.add_field(name="Avant", value=str(before.self_deaf), inline=True)
            embed.add_field(name="Apres", value=str(after.self_deaf), inline=True)

            await self.send_log(member.guild, "voice_logs", embed)

        if before.self_stream != after.self_stream:
            embed = self.make_embed(
                title="Stream vocal",
                description=f"Changement de stream pour {member.mention}.",
                color=discord.Color.blurple()
            )
            embed.add_field(name="Membre", value=self.user_string(member), inline=False)
            embed.add_field(name="Actif", value=str(after.self_stream), inline=False)

            await self.send_log(member.guild, "voice_logs", embed)

        if before.self_video != after.self_video:
            embed = self.make_embed(
                title="Camera vocale",
                description=f"Changement de camera pour {member.mention}.",
                color=discord.Color.blurple()
            )
            embed.add_field(name="Membre", value=self.user_string(member), inline=False)
            embed.add_field(name="Active", value=str(after.self_video), inline=False)

            await self.send_log(member.guild, "voice_logs", embed)


async def setup(bot):
    await bot.add_cog(Logs(bot))
