   

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
    # Chill / Casual Discord vibes & Natural Quotes
    "Need another cup of coffee to power through this grind.",
    "Late night sessions just hit completely differently.",
    "Small steps every single day lead to massive results.",
    "Time flies so fast when you're actually having fun.",
    "Consistency always beats raw motivation in the long run.",
    "Stay focused on your own lane and keep leveling up.",
    "Good music makes any grind ten times more enjoyable.",
    "Every master was once a beginner who refused to quit.",
    "Take a breath, reset your mind, and keep moving forward.",
    "Hard work beats talent when talent doesn't put in the work.",
    "A smooth sea never made a skilled sailor.",
    "Dream big, stay humble, and let your results speak.",
    "The secret to getting ahead is simply having the courage to start.",
    "Patience and persistence will overcome almost any obstacle.",
    "One day or day one, you always get to decide.",
    "Focus on the process, the progress will follow naturally.",
    "Never regret a day in your life, good days give joy, bad days give experience.",
    "Energy flows where your attention goes.",
    "Stay curious and keep exploring new horizons every day.",
    "Sometimes the best move is just to stay quiet and observe.",
    "Great things never come from staying inside comfort zones.",
    "Progress is progress, no matter how small it looks today.",
    "Silence is sometimes the loudest answer in the room.",
    "Discipline will take you places where motivation cannot.",
    "Trust the timing of your life and keep putting in the reps.",
    "Don't count the days, make every single day count.",
    "Simplicity is the ultimate sophistication.",
    "Keep your eyes on the stars and your feet on the ground.",
    "Success isn't owned, it's leased, and rent is due every day.",
    "Action cures anxiety and doubt every single time.",
    "Stay sharp, stay humble, and keep building quietly.",
    "Nothing worth having ever comes easy.",
    "Focus on being productive instead of just being busy.",
    "A journey of a thousand miles begins with a single step.",
    "Believe in the power of compound interest, in skills and life.",
    "Work hard in silence and let your success make all the noise.",
    "You don't have to be extreme, just consistent.",
    "The only person you should try to be better than is who you were yesterday."
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