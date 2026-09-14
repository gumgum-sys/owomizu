import asyncio
import json
import re
import time as _time

from discord.ext import commands


try:
    with open("utils/emojis.json", "r", encoding="utf-8") as file:
        emoji_dict = json.load(file)
except (FileNotFoundError, json.JSONDecodeError):
    emoji_dict = {}

RANK_WEIGHTS = {
    "hidden": 100,
    "fabled": 90,
    "legendary": 85,
    "gem": 80,
    "mythical": 70,
    "epic": 60,
    "rare": 40,
    "uncommon": 20,
    "common": 10,
}


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


def get_ranked_animals(text, lookup=None):
    if lookup is None:
        lookup = emoji_dict
    pattern = re.compile(
        r"<a:[a-zA-Z0-9_]+:[0-9]+>|:[a-zA-Z0-9_]+:|[\U0001F300-\U0001F6FF\U0001F700-\U0001F77F]"
    )
    matches = pattern.findall(text)
    items = []
    for c in matches:
        if c in lookup:
            data = lookup[c]
            name = data.get("name")
            rank = data.get("rank", "common").lower()
            price = data.get("sell_price", 0)
            weight = RANK_WEIGHTS.get(rank, 1)
            items.append((weight, price, name, rank))

    # Sort descending: primary by rarity weight, secondary by sell_price
    items.sort(key=lambda x: (x[0], x[1]), reverse=True)

    unique = []
    seen = set()
    for weight, price, name, rank in items:
        if name not in seen:
            seen.add(name)
            unique.append({"name": name, "rank": rank, "weight": weight, "price": price})
    return unique


class Others(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.zoo = False
        self._crate_paused_until = 0.0
        self._lootbox_paused_until = 0.0
        self.current_team = []
        self._last_zoo_audit = 0.0
        self._team_updating = False
        self._audit_task = None

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

    async def cog_load(self):
        auto_team = self.bot.settings_dict.get("autoTeam", {})
        if auto_team.get("enabled", True):
            self._audit_task = asyncio.create_task(self._team_audit_loop())
        # Startup: buka semua crate di inventory lalu trigger weapon check
        asyncio.create_task(self._startup_open_crates())

    async def cog_unload(self):
        if self._audit_task and not self._audit_task.done():
            self._audit_task.cancel()

    async def _startup_open_crates(self):
        """Pas startup, tunggu bot ready, buka semua crate, lalu auto-equip weapon terbaik."""
        await self.bot.wait_until_ready()
        await asyncio.sleep(self.bot.random.uniform(20.0, 30.0))
        auto_use = self.bot.settings_dict.get("autoUse", {})
        if auto_use.get("autoCrate", False):
            await self.bot.log("🎁 Startup: Opening available crates...", "#E7DA90")
            crate_cmd = {
                "cmd_name": self.bot.alias["crate"]["normal"],
                "cmd_arguments": "all",
                "prefix": True,
                "checks": False,
                "id": "crate",
            }
            await self.bot.put_queue(crate_cmd, priority=True)
            # Weapon check 8 detik setelah crate dibuka
            inv_cog = self.bot.get_cog("Inventory")
            if inv_cog and hasattr(inv_cog, "trigger_check"):
                asyncio.create_task(inv_cog.trigger_check(delay=8.0))

    async def _team_audit_loop(self):
        await self.bot.wait_until_ready()
        await asyncio.sleep(self.bot.random.uniform(8.0, 15.0))

        # Initial check on startup if team isn't populated
        if not self.current_team:
            await self.request_team_refresh(force=True)

        while not self.bot.is_closed():
            try:
                auto_team = self.bot.settings_dict.get("autoTeam", {})
                if not auto_team.get("enabled", True):
                    break
                interval_min = auto_team.get("checkIntervalMinutes", 30)
                await asyncio.sleep(interval_min * 60)
                await self.request_team_refresh(force=False)
            except asyncio.CancelledError:
                break
            except Exception as e:
                await self.bot.log(f"Error in team audit loop: {e}", "#c25560")
                await asyncio.sleep(60)

    async def request_team_refresh(self, force=False):
        now = _time.time()
        if self.bot.cmds_state.get("zoo", {}).get("in_queue", False):
            return
        if not force and (now - self._last_zoo_audit < 180 or self._team_updating):
            return
        self._last_zoo_audit = now
        self.zoo = True
        zoo_cmd = {
            "cmd_name": self.bot.alias["zoo"]["normal"],
            "prefix": True,
            "checks": False,
            "retry_count": 0,
            "id": "zoo",
        }
        await self.bot.sleep_till([1.5, 3.0])
        await self.bot.put_queue(zoo_cmd, priority=True)
        await self.bot.log("🦁 Requesting Zoo audit for optimal battle team...", "#4db6c4")

    async def on_rare_catch(self, catch_data):
        auto_team = self.bot.settings_dict.get("autoTeam", {})
        if not auto_team.get("enabled", True) or not auto_team.get("rotateOnRareCatch", True):
            return

        rarity_label = catch_data.get("rarity", "rare").lower()
        caught_weight = RANK_WEIGHTS.get(rarity_label, 1)

        # Hanya trigger kalau hewan baru LEBIH BAGUS dari member terlemah di tim
        current_min = getattr(self, "_current_team_min_weight", 0)
        if self.current_team and caught_weight <= current_min:
            await self.bot.log(
                f"⏭️ Skipping team audit — caught {rarity_label.upper()} (w={caught_weight}) "
                f"not better than current team min (w={current_min})", "#888888"
            )
            return

        await self.bot.log(f"🌟 Upgrade potential! Caught {rarity_label.upper()} (w={caught_weight}) > team min (w={current_min}). Auditing...", "#ffd43b")
        await asyncio.sleep(self.bot.random.uniform(2.5, 5.0))
        # force=False → pakai cooldown 180s supaya tidak spam
        await self.request_team_refresh(force=False)

    async def _apply_battle_team(self, animals):
        self._team_updating = True
        self.bot.user_status["team_updating"] = True
        try:
            names = [a["name"] for a in animals]
            desc = ", ".join(f"{idx+1}:{a['name']} ({a['rank'].upper()})" for idx, a in enumerate(animals))
            await self.bot.log(f"⚔️ Rotating Battle Team positions: {desc}", "#ffd43b")
            self.bot.add_dashboard_log("battle", f"Rotating team: {desc}", "info")

            # Clear team first to avoid slot swap collisions
            clear_cmd = {
                "cmd_name": "team",
                "cmd_arguments": "clear",
                "prefix": True,
                "checks": False,
                "retry_count": 0,
                "id": "team_clear",
            }
            await self.bot.put_queue(clear_cmd, priority=True)
            await asyncio.sleep(self.bot.random.uniform(2.0, 3.0))

            # Directly set positions 1, 2, 3 using discrete command IDs
            slot_ids = ["team_1", "team_2", "team_3"]
            for idx, beast in enumerate(animals[:3]):
                pos = idx + 1
                add_cmd = {
                    "cmd_name": "team",
                    "cmd_arguments": f"add {beast['name']} {pos}",
                    "prefix": True,
                    "checks": False,
                    "retry_count": 0,
                    "id": slot_ids[idx],
                }
                await self.bot.put_queue(add_cmd, priority=True)
                await asyncio.sleep(self.bot.random.uniform(1.0, 1.8))

            self.current_team = names
            self._current_team_min_weight = min(a["weight"] for a in animals)
            await self.bot.log(f"✅ Battle Team Rotation Complete: {names} (min_weight={self._current_team_min_weight})", "#51cf66")
            self.bot.add_dashboard_log("battle", f"Team updated: {', '.join(names)}", "success")

            # Trigger weapon check to auto-equip top weapons to new team members
            inv_cog = self.bot.get_cog("Inventory")
            if inv_cog and hasattr(inv_cog, "equip_team_weapons"):
                asyncio.create_task(inv_cog.equip_team_weapons(names))

            # --- Dynamic Era Evolution: auto-adjust sell rarity scope based on team tier ---
            lowest_weight = min(a["weight"] for a in animals)
            if lowest_weight >= 80:        # Legendary / Gem / Fabled (All team members Legendary+)
                era_name = "LEGENDARY ERA 👑"
                sell_rarity = ["c", "u", "r", "e", "m"]
            elif lowest_weight >= 70:      # Mythical
                era_name = "MYTHICAL ERA 🔮"
                sell_rarity = ["c", "u", "r", "e"]
            elif lowest_weight >= 60:      # Epic
                era_name = "EPIC ERA ⚡"
                sell_rarity = ["c", "u", "r"]
            else:                          # Rare (default)
                era_name = "RARE ERA 🌿"
                sell_rarity = ["c", "u"]

            current_rarity = self.bot.settings_dict["commands"]["sell"].get("rarity", ["c", "u"])
            if current_rarity != sell_rarity:
                self.bot.settings_dict["commands"]["sell"]["rarity"] = sell_rarity
                await self.bot.log(
                    f"📈 Era Evolution → [{era_name}] Sell scope: {current_rarity} → {sell_rarity}", "#ff9500"
                )
                self.bot.add_dashboard_log("battle", f"Era upgraded: {era_name} | sell: {sell_rarity}", "success")
            else:
                await self.bot.log(f"📊 [{era_name}] Sell scope stable: {sell_rarity}", "#888888")

        except Exception as e:
            await self.bot.log(f"Error rotating battle team: {e}", "#c25560")
        finally:
            await asyncio.sleep(2.5)
            self._team_updating = False
            self.bot.user_status["team_updating"] = False

    @commands.Cog.listener()
    async def on_message(self, message):
        nick = self.bot.get_nick(message)
        if (
            message.channel.id != self.bot.channel_id
            or message.author.id != self.bot.owo_bot_id
        ):
            return

        content = self.bot.extract_text(message)
        content_lower = content.lower()

        embed_info = ""
        if message.embeds:
            emb = message.embeds[0]
            emb_author = emb.author.name if (emb.author and emb.author.name) else ""
            emb_title = emb.title or ""
            emb_desc = (emb.description[:60] + "...") if emb.description else ""
            label = emb_title or emb_author or emb_desc
            if label:
                embed_info = f" [Embed: {label}]"
        await self.bot.log(f"OwO says: {content}{embed_info}", "#888888")

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
            "** you received a **weapon crate**!" in content_lower
            or "you found a **weapon crate**!" in content_lower
        ):
            if auto_use.get("autoCrate", False):
                if now < self._crate_paused_until:
                    return
                await self.bot.log("Found Crate! Using it...", "#E7DA90")
                await asyncio.sleep(self.bot.random.uniform(2.0, 4.0))
                await self.bot.put_queue(self.crate_cmd)
                inv_cog = self.bot.get_cog("Inventory")
                if inv_cog and hasattr(inv_cog, "trigger_check"):
                    asyncio.create_task(inv_cog.trigger_check(delay=6.0))

        elif (
            "** you received a **lootbox**!" in content_lower
            or "you found a **lootbox**!" in content_lower
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

        elif "inventory ======" in content_lower:
            if auto_use.get("autoCrate", False) and ("crate" in content_lower or "`100`" in content):
                if now >= self._crate_paused_until:
                    await self.bot.log("Found Crates in Inventory! Opening all...", "#E7DA90")
                    await asyncio.sleep(self.bot.random.uniform(2.0, 3.5))
                    crate_cmd = {
                        "cmd_name": "crate",
                        "cmd_arguments": "all",
                        "prefix": True,
                        "checks": False,
                        "id": "crate",
                    }
                    await self.bot.put_queue(crate_cmd, priority=True)


            if auto_use.get("autoLootbox", False) and ("box" in content_lower or "`050`" in content):
                if now >= self._lootbox_paused_until:
                    await self.bot.log("Found Lootbox in Inventory! Opening all...", "#E7DA90")
                    await asyncio.sleep(self.bot.random.uniform(2.0, 3.5))
                    lootbox_cmd = {
                        "cmd_name": "lootbox",
                        "cmd_arguments": "all",
                        "prefix": True,
                        "checks": False,
                        "id": "lootbox",
                    }
                    await self.bot.put_queue(lootbox_cmd, priority=True)
                    self.bot.user_status["no_gems"] = False

        elif "you currently have" in content_lower and "cowoncy" in content_lower:
            m = re.search(r'have\s+[\*_]*([0-9,]+)[\*_]*\s+cowoncy', content, re.IGNORECASE)
            if m:
                cash_val = int(m.group(1).replace(',', ''))
                await self.bot.update_cash(cash_val, override=True)
                await self.bot.log(f"Synced Cowoncy Balance: {cash_val:,}", "#51cf66")

        elif (
            "team add {animal}" in content_lower
            or "team add" in content_lower
            or "you do not have an active battle team" in content_lower
        ):
            await self.request_team_refresh(force=True)

        elif "zoo!" in content_lower and self.zoo:
            self.zoo = False
            ranked_animals = get_ranked_animals(content)
            if not ranked_animals:
                await self.bot.log("Zoo audit: No animals found in zoo response.", "#c25560")
                return

            best_3 = ranked_animals[:3]
            target_names = [a["name"] for a in best_3]

            if self.current_team == target_names:
                await self.bot.log(f"🛡️ Battle team is already optimal: {target_names}", "#51cf66")
                return

            await self._apply_battle_team(best_3)


async def setup(bot):
    await bot.add_cog(Others(bot))