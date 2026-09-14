import asyncio
import time
import re
from discord.ext import commands
from discord.ext.commands import ExtensionNotLoaded

TIER_SCORES = {
    # Mythic Tier (base 1000)
    "glacial axe": 1000,
    "abyssal glaive": 1000,
    "scythe of the reaper": 1000,

    # Fabled Tier (base 900)
    "fabled": 900,

    # Legendary Tier (base 800)
    "flame wand": 800,
    "poison dagger": 800,

    # Epic Tier (base 600)
    "staff of corruption": 600,
    "culling scythe": 600,
    "energy blade": 600,
    "greatsword": 600,

    # Rare Tier (base 400)
    "fine foul fish": 400,
    "foul fish": 400,
    "vampiric staff": 400,
    "bow": 400,
    "staff": 400,
    "axe": 400,
    "mace": 400,

    # Uncommon Tier (base 200)
    "sword": 200,
    "dagger": 200,

    # Common Tier (base 100)
    "stick": 100,
}

MAGIC_PETS = {"gdeer", "gcamel", "owl", "bat", "raven", "swan", "peacock"}
MAGIC_WEAPONS = {"staff", "wand", "orb", "tome", "grimoire", "rod"}
BRUISER_PETS = {"glion", "bear", "rhino", "elephant", "boar", "wolf"}
BRUISER_WEAPONS = {"axe", "greatsword", "hammer", "shield", "glaive"}
ASSASSIN_PETS = {"gfox", "tiger", "cheetah", "panther", "snake"}
ASSASSIN_WEAPONS = {"scythe", "dagger", "blade", "sword", "bow"}

def is_magic_weapon(w_name: str) -> bool:
    nl = w_name.lower()
    return any(k in nl for k in MAGIC_WEAPONS)

def is_magic_pet(p_name: str) -> bool:
    return p_name.lower() in MAGIC_PETS

def is_bruiser_pet(p_name: str) -> bool:
    return p_name.lower() in BRUISER_PETS

def is_assassin_pet(p_name: str) -> bool:
    return p_name.lower() in ASSASSIN_PETS

# Regex for modern OwO weapon list:
# Example: `FMX1NN` <:mythic:416520808501084162><:mgaxe:618389128949661716><:edischarge:572285187044671489> **Glacial Axe** 81% ➤  :dragon: dragon
# Example: `FMX1NJ` <:epic:416520722987614208><:esythe:618001307562672128><:elwolf:1474602314206679120> **Culling Scythe [0]** 62%
# Example: `FMX1NM` <:rare:416520066629107712><:rbow:535283613374349316><:ckno:1155427304663691294> **Bow** 42%
MODERN_WEAPON_REGEX = re.compile(
    r'[`]?([A-Z0-9]{5,8})[`]?\s*(?:<a?:[a-zA-Z0-9_]+:\d+>\s*)*\s*\*\*(.*?)(?:\s*\[(\d+)\])?\*\*\s*(\d+(?:\.\d+)?%)(?:\s*[\u27a4\>\-]+\s*(?:<a?:[a-zA-Z0-9_]+:\d+>\s*|:[a-zA-Z0-9_]+:\s*)*([a-zA-Z0-9_]+))?',
    re.IGNORECASE
)

# Legacy fallback pattern (e.g. 123 | Iron Sword (50 dmg))
LEGACY_WEAPON_REGEX = re.compile(
    r'(\d+)\s*\|\s*(.*?)\s*\((\d+)\s*dmg\)',
    re.IGNORECASE
)


class Inventory(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.checking = False
        self.last_check = 0
        self._loop_task = None
        self._reset_task = None
        self.equipped_weapons = {}  # {animal_name: weapon_id}

        self.inv_cmd = {
            "cmd_name": "weapon",
            "cmd_arguments": "",
            "prefix": True,
            "checks": False,
            "retry_count": 0,
            "id": "weapon",
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
        if self._reset_task and not self._reset_task.done():
            self._reset_task.cancel()

    async def trigger_check(self, delay=0.0):
        if delay > 0:
            await asyncio.sleep(delay)
        cnf = self.bot.settings_dict.get("autoEquip", {})
        if not cnf.get("enabled", False):
            return

        self.checking = True
        self.last_check = time.time()
        await self.bot.put_queue(self.inv_cmd, priority=True)
        await self.bot.log("🗡️ Checking weapon arsenal for team upgrades...", "#4db6c4")

        # Auto-reset checking flag after 25s so it never gets permanently stuck
        if self._reset_task and not self._reset_task.done():
            self._reset_task.cancel()
        self._reset_task = asyncio.create_task(self._auto_reset_checking(25.0))

    async def _auto_reset_checking(self, timeout=25.0):
        await asyncio.sleep(timeout)
        self.checking = False

    async def equip_team_weapons(self, team_names=None):
        """Called when team rotates to immediately equip weapons."""
        await asyncio.sleep(2.0)
        await self.trigger_check()

    def _get_active_team(self):
        others = self.bot.get_cog("Others")
        if others and hasattr(others, "current_team") and others.current_team:
            filtered = [p for p in others.current_team if p != "gcamel"]
            if filtered:
                return filtered
        return ["glion", "gdeer", "gfox"]

    async def inventory_loop(self):
        await self.bot.wait_until_ready()
        await asyncio.sleep(4)

        # Fast-track startup weapon equipping for active squad
        known_god_weapons = [
            ("glion", "FMX1NN", "Glacial Axe (Mythic 81%)"),
            ("gdeer", "FN2XJG", "Staff of Corruption (Epic 67.2%)"),
            ("gfox", "FN269J", "Culling Scythe (Epic 67.6%)")
        ]
        for i, (pet, wid, label) in enumerate(known_god_weapons):
            cmd = {
                "cmd_name": "weapon",
                "cmd_arguments": f"{wid} {pet}",
                "prefix": True,
                "checks": False,
                "retry_count": 0,
                "id": f"equip_{i+1}",
            }
            await self.bot.log(f"⚔️ Auto-Equip (Startup): Arming {pet} with {label} [ID: {wid}]!", "#a5d6a7")
            await self.bot.put_queue(cmd, priority=True)
            self.equipped_weapons[pet] = wid
            await asyncio.sleep(3.0)

        await asyncio.sleep(6)
        await self.trigger_check()

        while not self.bot.is_closed():
            try:
                cnf = self.bot.settings_dict.get("autoEquip", {})
                if not cnf.get("enabled", False):
                    break

                interval = cnf.get("interval_minutes", 60) * 60

                if time.time() - self.last_check > interval:
                    await self.trigger_check()

                await asyncio.sleep(60)

            except asyncio.CancelledError:
                break
            except Exception as e:
                await self.bot.log(f"Error in weapon inventory loop: {e}", "#c25560")
                await asyncio.sleep(60)

    def _calculate_weapon_score(self, name: str, quality_str: str, raw_line: str = "") -> float:
        clean_name = name.strip().lower()

        base_tier = 0
        # Priority 1: Check actual Discord emoji tag from OwO (ground truth tier)
        if raw_line:
            raw_lower = raw_line.lower()
            if any(tag in raw_lower for tag in ["<:mythic", "<a:mythic", "tier_m", "<:m_"]):
                base_tier = 1000
            elif any(tag in raw_lower for tag in ["<:fabled", "<a:fabled", "tier_f", "<:f_"]):
                base_tier = 900
            elif any(tag in raw_lower for tag in ["<:legendary", "<a:legendary", "tier_l", "<:l_"]):
                base_tier = 800
            elif any(tag in raw_lower for tag in ["<:epic", "<a:epic", "tier_e", "<:e_"]):
                base_tier = 600
            elif any(tag in raw_lower for tag in ["<:rare", "<a:rare", "tier_r", "<:r_"]):
                base_tier = 400
            elif any(tag in raw_lower for tag in ["<:uncommon", "<a:uncommon", "tier_u", "<:u_"]):
                base_tier = 200
            elif any(tag in raw_lower for tag in ["<:common", "<a:common", "tier_c", "<:c_"]):
                base_tier = 100

        # Priority 2: Fallback to known weapon name mapping if no emoji was matched
        if base_tier == 0:
            for known_name, score in TIER_SCORES.items():
                if known_name in clean_name:
                    base_tier = score
                    break

        if base_tier == 0:
            base_tier = 50

        try:
            quality = float(quality_str.replace("%", "").strip())
        except ValueError:
            quality = 0.0

        return float(base_tier) + quality

    async def equip_team_weapons(self, team=None):
        """Can be called externally by Others cog when team rotates"""
        await asyncio.sleep(2.0)
        await self.trigger_check()

    async def _handle_weapon_message(self, message):
        if message.channel.id != self.bot.channel_id:
            return
        if message.author.id != self.bot.owo_bot_id:
            return

        text = self.bot.extract_text(message)
        text_lower = text.lower()

        # Check for equip confirmation: "**🗡 | User**, :pet: **pet** is now wielding Weapon!"
        if "is now wielding" in text_lower:
            m_wield = re.search(r'\*\*([a-zA-Z0-9_]+)\*\*\s+is now wielding.*?\*\*(.*?)\*\*', text, re.IGNORECASE)
            if m_wield:
                pet_name = m_wield.group(1).lower()
                weapon_name = m_wield.group(2)
                await self.bot.log(f"✅ Weapon Equip Confirmed: {pet_name} is wielding {weapon_name}!", "#51cf66")
                self.bot.add_dashboard_log("inventory", f"{pet_name} wielding {weapon_name}", "success")
            else:
                await self.bot.log(f"✅ Weapon Equip Confirmed by OwO!", "#51cf66")

        if not self.checking:
            return

        # Ignore obvious non-weapon messages
        if any(term in text_lower for term in ["goes into battle!", "battle!", "spent 5", "zoo!", "inventory ======"]):
            return

        # Check if this is the weapon list
        if "weapons" not in text_lower and "weapon filters:" not in text_lower and "fmx1" not in text_lower:
            return

        try:
            parsed_weapons = []

            # Try modern regex line by line
            for line in text.split("\n"):
                m = MODERN_WEAPON_REGEX.search(line)
                if m:
                    wid = m.group(1).upper()
                    name = m.group(2).strip()
                    slot = m.group(3)  # e.g. '0'
                    stat_str = m.group(4)
                    wielder = m.group(5)  # e.g. 'dragon', 'tiger', 'penguin'
                    score = self._calculate_weapon_score(name, stat_str, line)
                    parsed_weapons.append({
                        "id": wid,
                        "name": name,
                        "slot": slot,
                        "quality": stat_str,
                        "wielder": wielder.lower() if wielder else None,
                        "score": score
                    })

            # Fallback legacy regex if modern didn't find any
            if not parsed_weapons:
                legacy_matches = LEGACY_WEAPON_REGEX.findall(text)
                for wid, name, dmg in legacy_matches:
                    dmg_val = float(dmg)
                    parsed_weapons.append({
                        "id": str(wid),
                        "name": name.strip(),
                        "slot": None,
                        "quality": f"{dmg} dmg",
                        "wielder": None,
                        "score": dmg_val
                    })

            if not parsed_weapons:
                return

            # Sort weapons by score descending
            parsed_weapons.sort(key=lambda w: w["score"], reverse=True)

            summary_items = []
            for w in parsed_weapons[:5]:
                wield_tag = f" ➤ {w['wielder']}" if w["wielder"] else ""
                summary_items.append(f"{w['name']} ({w['id']}, {w['quality']}{wield_tag})")
            summary = ", ".join(summary_items)
            await self.bot.log(f"🗡️ Weapons scanned: {summary}", "#4db6c4")
            self.bot.add_dashboard_log("inventory", f"Weapons scanned: {len(parsed_weapons)} found", "info")

            # Multi-Equip for active squad with role-based synergy
            active_team = self._get_active_team()

            pet_assignments = {}
            remaining_weapons = list(parsed_weapons)

            # 1. Magic pets (gdeer, etc.) -> Best Magic weapon (Staff, Wand, Orb)
            for pet in active_team:
                if is_magic_pet(pet):
                    best_mw = None
                    for w in remaining_weapons:
                        if is_magic_weapon(w["name"]):
                            best_mw = w
                            break
                    if best_mw:
                        pet_assignments[pet] = best_mw
                        remaining_weapons.remove(best_mw)

            # 2. Bruiser pets (glion, etc.) -> Heavy Cleave/Tank weapon (Axe, Greatsword, etc.)
            for pet in active_team:
                if pet not in pet_assignments and is_bruiser_pet(pet):
                    best_bw = None
                    for w in remaining_weapons:
                        nl = w["name"].lower()
                        if any(kw in nl for kw in BRUISER_WEAPONS):
                            best_bw = w
                            break
                    if not best_bw and remaining_weapons:
                        for w in remaining_weapons:
                            if not is_magic_weapon(w["name"]):
                                best_bw = w
                                break
                    if best_bw:
                        pet_assignments[pet] = best_bw
                        remaining_weapons.remove(best_bw)

            # 3. Assassin pets (gfox, etc.) -> Scythe / Dagger / Burst weapon
            for pet in active_team:
                if pet not in pet_assignments and is_assassin_pet(pet):
                    best_aw = None
                    for w in remaining_weapons:
                        if "scythe" in w["name"].lower():
                            best_aw = w
                            break
                    if not best_aw:
                        for w in remaining_weapons:
                            nl = w["name"].lower()
                            if any(kw in nl for kw in ASSASSIN_WEAPONS):
                                best_aw = w
                                break
                    if not best_aw and remaining_weapons:
                        for w in remaining_weapons:
                            if not is_magic_weapon(w["name"]):
                                best_aw = w
                                break
                    if best_aw:
                        pet_assignments[pet] = best_aw
                        remaining_weapons.remove(best_aw)

            # 4. Fallback for any unassigned pet
            for pet in active_team:
                if pet not in pet_assignments and remaining_weapons:
                    pet_assignments[pet] = remaining_weapons.pop(0)

            # Equip assigned weapons
            for idx, pet in enumerate(active_team):
                target_weapon = pet_assignments.get(pet)
                if not target_weapon:
                    continue

                # Check if already wielded by this pet
                is_equipped = False
                if target_weapon.get("wielder") and target_weapon["wielder"].lower() == pet.lower():
                    is_equipped = True
                elif self.equipped_weapons.get(pet) == target_weapon["id"]:
                    is_equipped = True

                if is_equipped:
                    await self.bot.log(
                        f"🛡️ Slot #{idx+1} ({pet}) already wielding '{target_weapon['name']}' (ID: {target_weapon['id']}, score: {target_weapon['score']:.1f})",
                        "#51cf66"
                    )
                    self.equipped_weapons[pet] = target_weapon["id"]
                else:
                    cmd = {
                        "cmd_name": "weapon",
                        "cmd_arguments": f"{target_weapon['id']} {pet}",
                        "prefix": True,
                        "checks": False,
                        "retry_count": 0,
                        "id": f"equip_{idx+1}",
                    }
                    await self.bot.log(
                        f"⚔️ Auto-Equip: Arming Slot #{idx+1} ({pet}) with '{target_weapon['name']}' (ID: {target_weapon['id']}, score: {target_weapon['score']:.1f})!",
                        "#a5d6a7"
                    )
                    self.bot.add_dashboard_log(
                        "inventory",
                        f"Arming {pet} with {target_weapon['name']} ({target_weapon['id']})",
                        "success"
                    )
                    await self.bot.put_queue(cmd, priority=True)
                    self.equipped_weapons[pet] = target_weapon["id"]
                    # If this weapon was previously mapped to another pet, invalidate it
                    for other_pet, wid in list(self.equipped_weapons.items()):
                        if other_pet != pet and wid == target_weapon["id"]:
                            self.equipped_weapons.pop(other_pet, None)
                    await asyncio.sleep(4.0)

            self.checking = False

        except Exception as e:
            self.checking = False
            await self.bot.log(f"Error parsing weapons: {e}", "#c25560")

    @commands.Cog.listener()
    async def on_message(self, message):
        await self._handle_weapon_message(message)

    @commands.Cog.listener()
    async def on_message_edit(self, before, after):
        await self._handle_weapon_message(after)


async def setup(bot):
    await bot.add_cog(Inventory(bot))