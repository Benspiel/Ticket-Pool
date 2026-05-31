import discord
from discord.ext import commands
import os
from dotenv import load_dotenv

load_dotenv()

intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.members = True

class TicketBot(commands.Bot):
    async def setup_hook(self):
        await self.load_extension("cogs.tickets")
        try:
            synced = await self.tree.sync()
            print(f"{len(synced)} Slash-Command(s) synchronisiert")
        except Exception as e:
            print(f"Slash-Commands konnten nicht synchronisiert werden: {e}")


bot = TicketBot(command_prefix="!", intents=intents)


@bot.event
async def on_ready():
    await bot.change_presence(activity=discord.CustomActivity(name="🟢| Öffen für Tickets"))
    print(f"Eingeloggt als {bot.user} (ID: {bot.user.id})")


bot.run(os.getenv("DISCORD_TOKEN"))
