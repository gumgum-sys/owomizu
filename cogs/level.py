   

import string
import random

from discord.ext import commands
from discord.ext.commands import ExtensionNotLoaded
import asyncio

from utils.danger import is_allowed

quotes_url = "https://favqs.com/api/qotd"

def generate_random_string(min, max):

    characters = string.ascii_lowercase + ' '
    length = random.randint(min,max)
    random_string = "".join(random.choice(characters) for _ in range(length))
    return random_string

FALLBACK_QUOTES = [
    "Stay focused and never give up on what you want to achieve.",
    "Small steps every day lead to big results over time.",
    "Hard work beats talent when talent doesn't work hard.",
    "Every new day is another chance to change your life.",
    "Focus on the journey, not just the destination.",
    "Patience and persistence will overcome almost anything.",
    "Dream big, stay humble, and dare to make mistakes.",
    "Consistency is the key to real mastery and success.",
    "A journey of a thousand miles begins with a single step.",
    "The secret of getting ahead is simply getting started.",
    "Believe you can and you're already halfway there.",
    "Keep moving forward no matter how slow you think you are."
]

async def fetch_quotes(session):
    try:
        async with session.get(quotes_url, timeout=5) as response:
            if response.status == 200:
                data = await response.json()
                quote = data.get("quote", {}).get("body")
                if quote and len(quote) < 140:
                    return quote
    except Exception:
        pass
    return random.choice(FALLBACK_QUOTES)

class Level(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self._loop_task = None
        self.cmd = {
            "cmd_name": None,
            "prefix": False,
            "checks": True,
            "id": "level"
        }

    async def cog_load(self):
        cnf = self.bot.settings_dict.get("commands", {}).get("lvlGrind", {})
        if not cnf.get("enabled", False):
            try:
                asyncio.create_task(self.bot.unload_cog("cogs.level"))
            except ExtensionNotLoaded:
                pass
        else:
            self._loop_task = asyncio.create_task(self.level_grind_loop())

    async def cog_unload(self):
        if self._loop_task and not self._loop_task.done():
            self._loop_task.cancel()
        await self.bot.remove_queue(id="level")

    async def level_grind_loop(self):
        await self.bot.wait_until_ready()
        await asyncio.sleep(self.bot.random.uniform(15.0, 25.0))

        while not self.bot.is_closed():
            try:
                cnf = self.bot.settings_dict.get("commands", {}).get("lvlGrind", {})
                if not cnf.get("enabled", False):
                    break

                cd_range = cnf.get("cooldown", [65, 95])
                cd = self.bot.random.uniform(cd_range[0], cd_range[1])
                await asyncio.sleep(cd)

                if not self.bot.command_handler_status.get("state", True):
                    continue

                if cnf.get("useQuoteInstead", True) and is_allowed("allowLevelQuotes"):
                    quote_text = await fetch_quotes(self.bot.session)
                else:
                    quote_text = generate_random_string(
                        cnf.get("minLengthForRandomString", 10),
                        cnf.get("maxLengthForRandomString", 20)
                    )

                self.cmd["cmd_name"] = quote_text
                await self.bot.put_queue(self.cmd)
                await self.bot.log(f"💬 Level Grind (XP Farm): \"{quote_text[:35]}...\"", "#977bab")

            except asyncio.CancelledError:
                break
            except Exception as e:
                await self.bot.log(f"Error in level_grind_loop: {e}", "#c25560")
                await asyncio.sleep(60)

async def setup(bot):
    await bot.add_cog(Level(bot))