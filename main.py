import os
import json
import asyncio
from pathlib import Path

import discord
from discord.ext import commands
from dotenv import load_dotenv

load_dotenv(dotenv_path=Path(__file__).with_name(".env"))

TOKEN = os.getenv("DISCORD_TOKEN")
DEFAULT_PREFIX = os.getenv("BOT_PREFIX", "+")
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


def get_prefix(bot, message):
    if not message.guild:
        return DEFAULT_PREFIX

    config = load_config()
    guild_data = config.get(str(message.guild.id), {})
    return guild_data.get("prefix", DEFAULT_PREFIX)


if not TOKEN:
    raise ValueError(
        "DISCORD_TOKEN introuvable. Verifie que le fichier .env existe bien et contient DISCORD_TOKEN=ton_token"
    )


intents = discord.Intents.default()
intents.guilds = True
intents.members = True
intents.messages = True
intents.message_content = True
intents.voice_states = True
intents.bans = True

bot = commands.Bot(
    command_prefix=get_prefix,
    intents=intents,
    help_command=None
)


@bot.event
async def on_ready():
    ensure_config_file()
    print(f"Connecte en tant que {bot.user} (ID: {bot.user.id})")
    print("Bot pret.")


@bot.command(name="ping")
async def ping(ctx):
    await ctx.send(f"Pong ! `{round(bot.latency * 1000)}ms`")


@bot.command(name="help")
async def help_command(ctx):
    prefix = get_prefix(bot, ctx.message)

    embed = discord.Embed(
        title="Commandes du bot",
        description="Liste des commandes disponibles",
        color=discord.Color.blurple()
    )

    embed.add_field(
        name=f"{prefix}autologs",
        value="Cree automatiquement la categorie et les salons de logs.",
        inline=False
    )
    embed.add_field(
        name=f"{prefix}configlogs",
        value="Affiche la configuration actuelle des logs.",
        inline=False
    )
    embed.add_field(
        name=f"{prefix}logtest",
        value="Envoie un embed de test dans les logs.",
        inline=False
    )
    embed.add_field(
        name=f"{prefix}setprefix <prefix>",
        value="Change le prefixe du bot pour ce serveur.",
        inline=False
    )
    embed.add_field(
        name=f"{prefix}ping",
        value="Affiche la latence du bot.",
        inline=False
    )

    await ctx.send(embed=embed)


async def load_extensions():
    await bot.load_extension("cogs.logs")


async def main():
    ensure_config_file()

    async with bot:
        await load_extensions()
        await bot.start(TOKEN)


if __name__ == "__main__":
    asyncio.run(main())
