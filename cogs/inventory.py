import asyncio
import time
import re
from discord.ext import commands
from discord.ext.commands import ExtensionNotLoaded


class Inventory(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.checking = False
        self.last_check = 0
        self.current_best_weapon = None
        self._loop_task = None

        self.inv_cmd = {
            "cmd_name": "weapon",
            "cmd_arguments": "",
            "prefix": True,
            "checks": True,
            "id": "weapon"
        }

        self.equip_cmd = {
            "cmd_name": "equip",
            "cmd_arguments": "",
            "prefix": True,
            "checks": True,
            "id": "equip"
        }

    async def cog_load(self):
        if not self.bot.settings_dict.get("autoEquip", {}).get("enabled", False):
            try:
                asyncio.create_task(self.bot.unload_cog("cogs.inventory"))
            except ExtensionNotLoaded:
                pass
        else:
            self._loop_task = asyncio.create_task(self.inventory_loop())

    async def cog_unload(self):
        if self._loop_task and not self._loop_task.done():
            self._loop_task.cancel()

    async def trigger_check(self, delay=0.0):
        if delay > 0:
            await asyncio.sleep(delay)
        cnf = self.bot.settings_dict.get("autoEquip", {})
        if not cnf.get("enabled", False):
            return
        if not self.checking:
            self.checking = True
            await self.bot.put_queue(self.inv_cmd, priority=True)
            self.last_check = time.time()
            await self.bot.log("🗡️ Checking weapon inventory for upgrades...", "#4db6c4")

    async def inventory_loop(self):
        await self.bot.wait_until_ready()
        await asyncio.sleep(18)  # brief startup delay
        # Initial check on startup
        await self.trigger_check()

        while not self.bot.is_closed():
            try:
                cnf = self.bot.settings_dict.get("autoEquip", {})
                if not cnf.get("enabled", False):
                    break

                interval = cnf.get("interval_minutes", 20) * 60

                if time.time() - self.last_check > interval:
                    await self.trigger_check()

                await asyncio.sleep(60)

            except asyncio.CancelledError:
                break
            except Exception as e:
                await self.bot.log(f"Error in weapon inventory loop: {e}", "#c25560")
                await asyncio.sleep(60)

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.channel.id != self.bot.channel_id:
            return

        if not self.checking:
            return

        if message.author.id != self.bot.owo_bot_id:
            return

        text_to_check = message.content or ""
        if message.embeds:
            for emb in message.embeds:
                if emb.title:
                    text_to_check += f" {emb.title}"
                if emb.description:
                    text_to_check += f" {emb.description}"
                for f in emb.fields:
                    text_to_check += f" {f.name} {f.value}"

        content_lower = text_to_check.lower()
        if "weapon" in content_lower or "inventory" in content_lower:
            try:
                weapons = re.findall(r"(\d+)\s*\|\s*(.*?)\s*\((\d+)\s*dmg\)", text_to_check, re.IGNORECASE)

                if not weapons:
                    self.checking = False
                    return

                best_weapon_id = None
                best_name = ""
                max_dmg = -1

                for wid, name, dmg in weapons:
                    dmg_val = int(dmg)
                    if dmg_val > max_dmg:
                        max_dmg = dmg_val
                        best_weapon_id = wid
                        best_name = name.strip()

                if best_weapon_id:
                    if best_weapon_id != self.current_best_weapon:
                        self.equip_cmd["cmd_arguments"] = str(best_weapon_id)
                        await self.bot.log(f"⚔️ Auto-Equip: Found stronger weapon '{best_name}' (ID: {best_weapon_id}, {max_dmg} dmg)!", "#a5d6a7")
                        self.bot.add_dashboard_log("inventory", f"Equipping weapon {best_weapon_id} ({best_name}, {max_dmg} dmg)", "info")
                        await self.bot.put_queue(self.equip_cmd, priority=True)
                        self.current_best_weapon = best_weapon_id
                    else:
                        await self.bot.log(f"⚔️ Best weapon already equipped (ID: {best_weapon_id}, {max_dmg} dmg)", "#51cf66")

                self.checking = False

            except Exception as e:
                self.checking = False
                await self.bot.log(f"Error parsing weapons: {e}", "#c25560")


async def setup(bot):
    await bot.add_cog(Inventory(bot))