import asyncio
import json
import re

from discord.ext import commands


try:
    with open("utils/emojis.json", "r", encoding="utf-8") as file:
        emoji_dict = json.load(file)
except (FileNotFoundError, json.JSONDecodeError):
    emoji_dict = {}


def parse_loot_reset_seconds(content: str):
    if "resets in" not in content.lower():
        return None
    total = 0
    h = re.search(r"(\d+)\s*h", content.lower())
    m = re.search(r"(\d+)\s*m", content.lower())
    s = re.search(r"(\d+)\s*s", content.lower())
    if h:
        total += int(h.group(1)) * 3600
    if m:
        total += int(m.group(1)) * 60
    if s:
        total += int(s.group(1))
    return total if total > 0 else None


def get_emoji_names(text, lookup=None):
    if lookup is None:
        lookup = emoji_dict
    pattern = re.compile(
        r"<a:[a-zA-Z0-9_]+:[0-9]+>|:[a-zA-Z0-9_]+:|[\U0001F300-\U0001F6FF\U0001F700-\U0001F77F]"
    )
    return [lookup[c]["name"] for c in pattern.findall(text) if c in lookup]


class Others(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.zoo = False
        self._crate_paused_until = 0.0
        self._lootbox_paused_until = 0.0

        self.lootbox_cmd = {
            "cmd_name": self.bot.alias["lootbox"]["normal"],
            "prefix": True,
            "checks": False,
            "slash_cmd_name": "lootbox",
            "id": "lootbox",
        }
        self.crate_cmd = {
            "cmd_name": self.bot.alias["crate"]["normal"],
            "prefix": True,
            "checks": False,
            "slash_cmd_name": "crate",
            "id": "crate",
        }

    @commands.Cog.listener()
    async def on_message(self, message):
        import time as _time

        nick = self.bot.get_nick(message)
        if (
            message.channel.id != self.bot.channel_id
            or message.author.id != self.bot.owo_bot_id
        ):
            return

        content = message.content
        content_lower = content.lower()

        if "**you must accept these rules to use the bot!**" in content_lower:
            await asyncio.sleep(self.bot.random.uniform(0.6, 1.7))
            if message.components and message.components[0].children[0]:
                try:
                    await message.components[0].children[0].click()
                except Exception:
                    pass
            return

        names_to_check = {
            self.bot.user.name.lower(),
            str(self.bot.user.id),
            nick.lower() if nick else "",
            (getattr(self.bot.user, 'global_name', None) or "").lower(),
            (getattr(self.bot.user, 'display_name', None) or "").lower()
        }
        names_to_check.discard("")

        matches_me = (
            any(name in content_lower for name in names_to_check)
            or f"<@{self.bot.user.id}>" in content
        )

        if not matches_me:
            return

        auto_use = self.bot.settings_dict.get("autoUse", {})
        now = _time.time()

        if (
            "** You received a **weapon crate**!" in content
            or "You found a **weapon crate**!" in content
        ):
            if auto_use.get("autoCrate", False):
                if now < self._crate_paused_until:
                    return
                await self.bot.log("Found Crate! Using it...", "#E7DA90")
                await asyncio.sleep(self.bot.random.uniform(2.0, 4.0))
                await self.bot.put_queue(self.crate_cmd)

        elif (
            "** You received a **lootbox**!" in content
            or "You found a **lootbox**!" in content
        ):
            if auto_use.get("autoLootbox", False):
                if now < self._lootbox_paused_until:
                    return
                await self.bot.log("Found Lootbox! Opening it...", "#E7DA90")
                await asyncio.sleep(self.bot.random.uniform(2.0, 4.0))
                await self.bot.put_queue(self.lootbox_cmd)
                self.bot.user_status["no_gems"] = False

        elif "you don't have any weapon crates" in content_lower or "no weapon crates" in content_lower:
            self._crate_paused_until = now + 86400
            await self.bot.log("No crates available. Pausing crate auto-use for 24h.", "#aaaaaa")

        elif "you don't have any lootboxes" in content_lower or "no lootboxes" in content_lower:
            self._lootbox_paused_until = now + 3600
            await self.bot.log("No lootboxes available. Pausing lootbox auto-use for 1h.", "#aaaaaa")

        elif "resets in" in content_lower and "weapon crate" in content_lower:
            secs = parse_loot_reset_seconds(content)
            if secs:
                self._crate_paused_until = now + secs + 10
                await self.bot.log(f"Crate resets in {secs}s. Auto-pause set.", "#aaaaaa")

        elif "resets in" in content_lower and "lootbox" in content_lower:
            secs = parse_loot_reset_seconds(content)
            if secs:
                self._lootbox_paused_until = now + secs + 10
                await self.bot.log(f"Lootbox resets in {secs}s. Auto-pause set.", "#aaaaaa")

        elif "you currently have" in content_lower and "cowoncy" in content_lower:
            m = re.search(r'have\s+[\*]*([0-9,]+)[\*]*\s+cowoncy', content, re.IGNORECASE)
            if m:
                cash_val = int(m.group(1).replace(',', ''))
                await self.bot.update_cash(cash_val, override=True)
                await self.bot.log(f"Synced Cowoncy Balance: {cash_val:,}", "#51cf66")

        elif (
            "team add {animal}" in content.lower()
            or "team add" in content.lower()
        ):
            self.zoo = True
            team_cmd = {
                "cmd_name": self.bot.alias["zoo"]["normal"],
                "prefix": True,
                "checks": False,
                "retry_count": 0,
                "id": "zoo",
            }
            await self.bot.sleep_till([2, 4])
            await self.bot.put_queue(team_cmd, priority=True)

        elif "zoo!" in content.lower() and self.zoo:
            animals = get_emoji_names(content)
            animals.reverse()
            await asyncio.sleep(self.bot.random.uniform(1.5, 2.3))
            for i in range(min(len(animals), 3)):
                zoo_cmd = {
                    "cmd_name": "team",
                    "cmd_arguments": f"add {animals[i]}",
                    "prefix": True,
                    "checks": False,
                    "retry_count": 0,
                    "id": "team",
                }
                await self.bot.put_queue(zoo_cmd, priority=True)
                await asyncio.sleep(self.bot.random.uniform(1.5, 2.3))
            self.zoo = False


async def setup(bot):
    await bot.add_cog(Others(bot))