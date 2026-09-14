# -*- coding: utf-8 -*-
"""AngryPeds for PyLoaderV 0.6.

Arms nearby pedestrians and makes them attack the player.
"""

from __future__ import annotations

import random
from pathlib import Path

import gta
from gta.natives import entity, misc, ped, player, task, weapon

INTERVAL_MS = 0
__priority__ = 60

VK = {
    "F1": 0x70, "F2": 0x71, "F3": 0x72, "F4": 0x73,
    "F5": 0x74, "F6": 0x75, "F7": 0x76, "F8": 0x77,
    "F9": 0x78, "F10": 0x79, "F11": 0x7A, "F12": 0x7B,
    "INSERT": 0x2D, "HOME": 0x24, "END": 0x23,
}

WEAPON_HASHES = {
    "knife": 0x99B507EA,
    "bat": 0x958A4A8F,
    "pistol": 0x1B06D571,
    "combatpistol": 0x5EF9FEC4,
    "microsmg": 0x13532244,
    "smg": 0x2BE6766B,
    "assaultrifle": 0xBFEFFF6D,
    "carbinerifle": 0x83BF0278,
    "pumpshotgun": 0x1D073A89,
    "sawnoffshotgun": 0x7846A318,
    "mg": 0x9D07F764,
    "combatmg": 0x7FD62962,
    "rpg": 0xB1CA77B1,
    "minigun": 0x42BF8A85,
    "railgun": 0x6D544C99,
    "widowmaker": 0xB62D1F67,
}

RANDOM_WEAPONS = [
    WEAPON_HASHES["knife"],
    WEAPON_HASHES["pistol"],
    WEAPON_HASHES["microsmg"],
    WEAPON_HASHES["assaultrifle"],
    WEAPON_HASHES["pumpshotgun"],
    WEAPON_HASHES["rpg"],
]

TOGGLE_KEY = VK["F10"]
TOGGLE_KEY_NAME = "F10"
AGGRO_RADIUS = 1000.0
GIVE_WEAPONS = True
INFINITE_AMMO = True
INFINITE_CLIP = False
WEAPONS_MODE = "random"
CUSTOM_LIST: list[int] = []
DEBUG = False
PROCESS_LIMIT_PER_TICK = 40

_scripts_dir = Path(__file__).resolve().parent
_config_file = _scripts_dir / "AngryPeds 0.3 Rus.ini"

_active = False
_processed: set[int] = set()
_tick_count = 0
_last_game_time = 0
_keys_down: set[int] = set()


def _log(msg: object) -> None:
    if DEBUG:
        gta.notify("~y~[AP]~w~ " + str(msg))
    gta.log("info" if DEBUG else "debug", "[AngryPeds] " + str(msg))


def _parse_bool(value: str) -> bool:
    return value.strip().lower() in {"true", "1", "yes", "on"}


def _parse_key(value: str) -> tuple[str, int]:
    raw = value.strip().upper()
    if raw in VK:
        return raw, VK[raw]
    if len(raw) == 1 and (raw.isalpha() or raw.isdigit()):
        return raw, ord(raw)
    return TOGGLE_KEY_NAME, TOGGLE_KEY


def _ensure_config() -> None:
    if _config_file.exists():
        return
    _config_file.write_text(
        "\n".join(
            [
                "[AngryPeds]",
                "",
                "# Toggle key",
                "ToggleKey=F10",
                "",
                "# Radius in meters",
                "AggroRadius=100.0",
                "",
                "# Give weapons (true/false)",
                "GiveWeapons=true",
                "",
                "# Infinite ammo (true/false)",
                "InfiniteAmmo=true",
                "",
                "# Infinite clip (true/false)",
                "InfiniteClip=false",
                "",
                "# Weapons: [random] or [pistol] or [pistol,knife ect...]",
                "Weapons=[pistol]",
                "",
                "# Interval in ms",
                "IntervalMS=500",
            ]
        ),
        encoding="utf-8",
    )


def _parse_weapon_token(token: str) -> int | None:
    value = token.strip().lower()
    if not value:
        return None
    if value in WEAPON_HASHES:
        return WEAPON_HASHES[value]
    try:
        return int(value, 16) if value.startswith("0x") else int(value, 10)
    except ValueError:
        return None


def _load_config() -> None:
    global TOGGLE_KEY, TOGGLE_KEY_NAME, AGGRO_RADIUS, GIVE_WEAPONS
    global INFINITE_AMMO, INFINITE_CLIP, INTERVAL_MS, WEAPONS_MODE
    global CUSTOM_LIST, DEBUG, PROCESS_LIMIT_PER_TICK

    _ensure_config()
    try:
        lines = _config_file.read_text(encoding="utf-8").splitlines()
    except Exception as exc:
        _log("Read config failed: " + str(exc))
        return

    for raw in lines:
        line = raw.strip()
        if not line or line.startswith(("#", ";", "[")) or "=" not in line:
            continue
        key, val = line.split("=", 1)
        key = key.strip().lower()
        val = val.strip()

        try:
            if key == "togglekey":
                TOGGLE_KEY_NAME, TOGGLE_KEY = _parse_key(val)
            elif key == "aggroradius":
                AGGRO_RADIUS = float(val)
            elif key == "giveweapons":
                GIVE_WEAPONS = _parse_bool(val)
            elif key == "infiniteammo":
                INFINITE_AMMO = _parse_bool(val)
            elif key == "infiniteclip":
                INFINITE_CLIP = _parse_bool(val)
            elif key == "intervalms":
                INTERVAL_MS = max(0, int(val))
            elif key == "processlimitpertick":
                PROCESS_LIMIT_PER_TICK = max(1, int(val))
            elif key == "debug":
                DEBUG = _parse_bool(val)
            elif key == "weapons":
                _load_weapon_config_value(val)
        except Exception as exc:
            _log(f"Config parse error for {key}: {exc}")


def _load_weapon_config_value(value: str) -> None:
    global WEAPONS_MODE, CUSTOM_LIST
    text = value.strip()
    if text.startswith("[") and text.endswith("]"):
        text = text[1:-1].strip()
    if text.lower() == "random":
        WEAPONS_MODE = "random"
        CUSTOM_LIST = []
        return

    parsed: list[int] = []
    for token in text.split(","):
        weapon_hash = _parse_weapon_token(token)
        if weapon_hash is not None:
            parsed.append(weapon_hash)
    WEAPONS_MODE = "list"
    CUSTOM_LIST = parsed or [WEAPON_HASHES["pistol"]]


def _get_weapon_hash() -> int:
    if WEAPONS_MODE == "random":
        return random.choice(RANDOM_WEAPONS)
    if not CUSTOM_LIST:
        return WEAPON_HASHES["pistol"]
    return random.choice(CUSTOM_LIST)


def _valid_ped(ped_handle: int, player_ped: int) -> bool:
    if ped_handle == 0 or ped_handle == player_ped:
        return False
    try:
        if not entity.DOES_ENTITY_EXIST(ped_handle):
            return False
        if entity.IS_ENTITY_DEAD(ped_handle, False):
            return False
        if ped.IS_PED_DEAD_OR_DYING(ped_handle, True):
            return False
        if ped.IS_PED_A_PLAYER(ped_handle):
            return False
        if not ped.IS_PED_HUMAN(ped_handle):
            return False
    except Exception:
        return False
    return True


def _within_radius(ped_handle: int, player_ped: int) -> bool:
    try:
        pp = entity.GET_ENTITY_COORDS(player_ped, True)
        p = entity.GET_ENTITY_COORDS(ped_handle, True)
        distance = misc.GET_DISTANCE_BETWEEN_COORDS(pp[0], pp[1], pp[2], p[0], p[1], p[2], True)
        return distance <= AGGRO_RADIUS
    except Exception:
        return False


def _give_weapon_to_ped(ped_handle: int, weapon_hash: int) -> None:
    ammo = 9999 if INFINITE_AMMO else 999
    weapon.GIVE_WEAPON_TO_PED(ped_handle, weapon_hash, ammo, False, True)
    if INFINITE_AMMO:
        weapon.SET_PED_INFINITE_AMMO(ped_handle, True, weapon_hash)
    if INFINITE_CLIP:
        weapon.SET_PED_INFINITE_AMMO_CLIP(ped_handle, True)


def _anger_ped(ped_handle: int, target_ped: int) -> None:
    # Combat tuning: more persistent and aggressive without relying on SHVDN tasks.
    ped.SET_PED_AS_ENEMY(ped_handle, True)
    ped.SET_PED_KEEP_TASK(ped_handle, True)
    ped.SET_PED_SEEING_RANGE(ped_handle, AGGRO_RADIUS)
    ped.SET_PED_HEARING_RANGE(ped_handle, AGGRO_RADIUS)
    ped.SET_PED_COMBAT_ABILITY(ped_handle, 2)      # professional
    ped.SET_PED_COMBAT_MOVEMENT(ped_handle, 2)     # offensive
    ped.SET_PED_COMBAT_RANGE(ped_handle, 2)        # far
    for attr in (0, 5, 13, 46):
        try:
            ped.SET_PED_COMBAT_ATTRIBUTES(ped_handle, attr, True)
        except Exception:
            pass
    task.TASK_COMBAT_PED(ped_handle, target_ped, 0, 16)


def _process_ped(ped_handle: int, target_ped: int) -> bool:
    if ped_handle in _processed:
        return False
    if not _valid_ped(ped_handle, target_ped):
        return False
    if not _within_radius(ped_handle, target_ped):
        return False
    try:
        if ped.IS_PED_IN_COMBAT(ped_handle, target_ped):
            return False
    except Exception:
        pass

    try:
        if GIVE_WEAPONS:
            _give_weapon_to_ped(ped_handle, _get_weapon_hash())
        _anger_ped(ped_handle, target_ped)
        _processed.add(ped_handle)
        return True
    except Exception as exc:
        _log("Process ped error: " + str(exc))
        return False


def on_start() -> None:
    global _last_game_time
    _load_config()
    _last_game_time = misc.GET_GAME_TIMER()
    _log(f"Ready. Toggle={TOGGLE_KEY_NAME} radius={AGGRO_RADIUS}")


def on_tick() -> None:
    global _tick_count, _last_game_time, _processed

    now = misc.GET_GAME_TIMER()
    elapsed = (now - _last_game_time) & 0xFFFFFFFF
    if elapsed < INTERVAL_MS:
        return
    _last_game_time = now
    if not _active:
        return

    target = player.PLAYER_PED_ID()
    try:
        if target == 0 or not entity.DOES_ENTITY_EXIST(target) or entity.IS_ENTITY_DEAD(target, False):
            return
    except Exception:
        return

    _tick_count += 1
    if _tick_count > 100:
        _tick_count = 0
        if len(_processed) > 1000:
            _processed = set()
            _log("Processed cache cleared.")

    processed_now = 0
    seen = 0
    for ped_handle in gta.get_all_peds():
        seen += 1
        if _process_ped(int(ped_handle), target):
            processed_now += 1
            if processed_now >= PROCESS_LIMIT_PER_TICK:
                break

    if DEBUG and processed_now:
        _log(f"armed={processed_now} seen={seen} cache={len(_processed)}")


def on_key_down(vk, down, shift, ctrl, alt) -> None:
    global _active, _processed, _tick_count
    vk = int(vk)
    if not down:
        _keys_down.discard(vk)
        return
    if vk in _keys_down:
        return
    _keys_down.add(vk)
    if vk != TOGGLE_KEY:
        return

    _active = not _active
    _processed = set()
    _tick_count = 0
    status = "~g~Вкл" if _active else "~r~Откл"
    gta.notify("Злые прохожие: " + status)


def on_aborted() -> None:
    global _active, _processed
    _active = False
    _processed = set()
    _log("Отмена.")
