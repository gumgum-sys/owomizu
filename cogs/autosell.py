import asyncio
import time
import re

from discord.ext import commands
from discord.ext.commands import ExtensionNotLoaded


class AutoSell(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.is_selling = False
        self.hunt_count = 0
        self.last_sell_time = 0

    async def cog_load(self):
        if not self.bot.settings_dict["autoSell"]["enabled"]:
            try:
                asyncio.create_task(self.bot.unload_cog("cogs.autosell"))
            except ExtensionNotLoaded:
                pass

    async def cog_unload(self):
        for r in ["c", "u", "r", "e", "m"]:
            await self.bot.remove_queue(id=f"autosell_{r}")

    async def trigger_auto_sell(self):
        try:
            if self.is_selling:
                return

            self.is_selling = True

            # Source of truth: commands.sell.rarity (diupdate era evolution otomatis)
            sell_rarities = (
                self.bot.settings_dict.get("commands", {})
                .get("sell", {})
                .get("rarity", None)
            )
            if not sell_rarities:
                sell_rarities = self.bot.settings_dict["autoSell"].get("sellCommand", ["c", "u"])
            if isinstance(sell_rarities, str):
                sell_rarities = [sell_rarities]

            action = self.bot.settings_dict.get("autoSell", {}).get("action", "sacrifice")
            cmd_action = "sac" if action in ("sacrifice", "sac") else "sell"
            action_name = "AutoSacrifice" if cmd_action == "sac" else "AutoSell"
            action_verb = "Sacrificing" if cmd_action == "sac" else "Selling"

            trigger_n = self.bot.settings_dict["autoSell"].get("triggerEveryNHunts", 5)
            await self.bot.log(
                f"🔮 {action_name} [tiap {trigger_n} hunt]: {action_verb} {sell_rarities} for {'Essence' if cmd_action == 'sac' else 'Cowoncy'}",
                "#a29bfe" if cmd_action == "sac" else "#ffd43b"
            )
            self.bot.add_dashboard_log("autosell", f"Hunt-triggered {action}: {sell_rarities}", "info")

            for idx, rarity in enumerate(sell_rarities):
                cmd = {
                    "cmd_name": cmd_action,
                    "cmd_arguments": rarity,
                    "prefix": True,
                    "checks": False,
                    "retry_count": 0,
                    "id": f"autosell_{rarity}",
                }
                await self.bot.put_queue(cmd, priority=True)
                if idx < len(sell_rarities) - 1:
                    await asyncio.sleep(self.bot.random.uniform(3.0, 5.0))

            self.hunt_count = 0
            self.last_sell_time = time.time()
            asyncio.create_task(self._reset_selling_flag(60))

        except Exception as e:
            self.is_selling = False
            await self.bot.log(f"Error in trigger_auto_sell: {e}", "#c25560")

    async def _reset_selling_flag(self, delay):
        await asyncio.sleep(delay)
        if self.is_selling:
            self.is_selling = False

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.channel.id != self.bot.cm.id:
            return
        if message.author.id != self.bot.owo_bot_id:
            return

        content = self.bot.extract_text(message)
        content_lower = content.lower()

        # Detect sacrifice completion (Essence gained)
        if "you sacrificed" in content_lower and "essence" in content_lower:
            m = re.search(r'gained \*\*([\d,]+)\*\* essence', content_lower) or re.search(r'gained ([\d,]+) essence', content_lower)
            essence = int(m.group(1).replace(',', '')) if m else 0
            await self.bot.log(f"✨ AutoSacrifice: Sacrificed animals! +{essence:,} essence", "#a29bfe")
            self.bot.add_dashboard_log("autosell", f"Sacrifice completed (+{essence:,} essence)", "success")
            return

        # Detect sell completion
        if "for a total of **<:cowoncy:" in content_lower:
            m = re.search(r'for a total of \*\*<:cowoncy:\d+> ([\d,]+)', content)
            earned = int(m.group(1).replace(',', '')) if m else 0
            await self.bot.log(f"✅ AutoSell: Sold animals! +{earned:,} cowoncy", "#51cf66")
            self.bot.add_dashboard_log("autosell", f"Sell completed (+{earned:,})", "success")
            if self.bot.settings_dict.get("cashCheck"):
                await self.bot.update_cash(earned)
            return

        if "couldn't find any animals" in content_lower or "no animals found" in content_lower:
            await self.bot.log("ℹ️ AutoSell/Sac: No animals found for this rarity.", "#888888")
            return

        # Detect hunt result: "gained **NNxp**!" — unik untuk hunt, bukan battle
        if "gained **" in content_lower and "xp**" in content_lower:
            nick = self.bot.get_nick(message)
            names_to_check = {
                self.bot.user.name.lower(),
                str(self.bot.user.id),
                (nick.lower() if nick else ""),
                (getattr(self.bot.user, "global_name", None) or "").lower(),
            }
            names_to_check.discard("")
            is_mine = (
                any(n in content_lower for n in names_to_check)
                or f"<@{self.bot.user.id}>" in content
            )
            if not is_mine:
                return

            self.hunt_count += 1
            trigger_n = self.bot.settings_dict["autoSell"].get("triggerEveryNHunts", 10)
            await self.bot.log(f"🎯 Hunt #{self.hunt_count}/{trigger_n}", "#888888")

            if self.hunt_count >= trigger_n:
                await self.trigger_auto_sell()


async def setup(bot):
    await bot.add_cog(AutoSell(bot))