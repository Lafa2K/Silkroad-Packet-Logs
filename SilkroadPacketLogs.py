from phBot import *
import QtBind
import os
import time
import json
import binascii
from collections import Counter

PLUGIN_NAME = "Silkroad Packet Logs"
PLUGIN_VERSION = "1.0"

gui = QtBind.init(__name__, PLUGIN_NAME)

QtBind.createLabel(gui, "Passive Silkroad packet/state logger", 10, 10)
QtBind.createButton(gui, "start_session", "START SESSION", 10, 40)
QtBind.createButton(gui, "stop_session", "STOP SESSION", 145, 40)
QtBind.createButton(gui, "snapshot_now", "SNAPSHOT NOW", 280, 40)

QtBind.createButton(gui, "mark_normal", "MARK NORMAL", 10, 80)
QtBind.createButton(gui, "mark_action", "MARK ACTION", 145, 80)
QtBind.createButton(gui, "mark_bug", "MARK BUG", 280, 80)

QtBind.createLabel(gui, "Nota:", 10, 125)
txtNote = QtBind.createLineEdit(gui, "", 50, 122, 310, 22)
QtBind.createButton(gui, "mark_note", "MARK NOTE", 370, 120)

# ------------------------------------------------------------
# CONFIG
# ------------------------------------------------------------

SNAPSHOT_INTERVAL = 1.0
PACKET_PREVIEW_BYTES = 256
FAST_PACKET_MS = 250

running = False
session_dir = None
files = {}

last_snapshot_at = 0.0
last_char = None
last_inventory = {}
last_job_pouch = {}
last_monsters = {}
last_pets = {}

last_client_opcode_time = {}

recent_zero_hp_monsters = {}
recent_inventory_gains = []


# ------------------------------------------------------------
# BASIC HELPERS
# ------------------------------------------------------------

def now_text():
    return time.strftime("%Y-%m-%d %H:%M:%S")


def now_float():
    return time.time()


def safe(v):
    if v is None:
        return ""
    return str(v)


def plugin_dir():
    try:
        return os.path.dirname(os.path.abspath(__file__))
    except:
        return os.getcwd()


def write_log(name, text):
    if not running:
        return

    f = files.get(name)
    if not f:
        return

    try:
        f.write("[%s] %s\n" % (now_text(), text))
        f.flush()
    except:
        pass


def write_json(name, event_type, payload):
    obj = {
        "time": now_text(),
        "ts": now_float(),
        "event": event_type,
        "data": payload
    }
    write_log(name, json.dumps(obj, ensure_ascii=False, sort_keys=True))


def packet_hex(data):
    try:
        raw = bytes(data)
        preview = raw[:PACKET_PREVIEW_BYTES]
        text = binascii.hexlify(preview).decode("ascii").upper()
        if len(raw) > PACKET_PREVIEW_BYTES:
            text += "...(+%d bytes)" % (len(raw) - PACKET_PREVIEW_BYTES)
        return text
    except:
        return "<unable-to-render>"


def marker(text):
    if not running:
        log("[SPL] Session is not running.")
        return

    line = "=" * 70
    write_log("markers", line)
    write_log("markers", text)
    write_log("markers", line)

    write_log("anomalies", "MARKER: " + text)
    log("[SPL] MARK: " + text)


# ------------------------------------------------------------
# NORMALIZERS
# ------------------------------------------------------------

def normalize_item(item):
    if not item:
        return None

    return {
        "name": item.get("name"),
        "servername": item.get("servername"),
        "model": item.get("model"),
        "quantity": item.get("quantity", 1),
        "plus": item.get("plus"),
    }


def inventory_map():
    result = {}

    try:
        inv = get_inventory() or {}
        items = inv.get("items", [])

        for slot, item in enumerate(items):
            if not item:
                continue

            obj = normalize_item(item)
            obj["slot"] = slot
            result[str(slot)] = obj
    except Exception as ex:
        write_log("anomalies", "get_inventory error: %s" % ex)

    return result


def pouch_map():
    result = {}

    try:
        pouch = get_job_pouch() or {}
        items = pouch.get("items", [])

        for slot, item in enumerate(items):
            if not item:
                continue

            obj = normalize_item(item)
            obj["slot"] = slot
            result[str(slot)] = obj
    except Exception as ex:
        write_log("anomalies", "get_job_pouch error: %s" % ex)

    return result


def item_totals(inv):
    totals = Counter()

    for _, item in inv.items():
        key = (
            safe(item.get("servername")),
            safe(item.get("model")),
            safe(item.get("name"))
        )
        try:
            qty = int(item.get("quantity", 1) or 1)
        except:
            qty = 1
        totals[key] += qty

    return totals


def monster_map():
    out = {}

    try:
        mons = get_monsters() or {}

        for uid, m in mons.items():
            out[str(uid)] = {
                "uid": uid,
                "name": m.get("name"),
                "servername": m.get("servername"),
                "model": m.get("model"),
                "type": m.get("type"),
                "region": m.get("region"),
                "x": m.get("x"),
                "y": m.get("y"),
                "hp": m.get("hp"),
                "max_hp": m.get("max_hp"),
                "attacking": m.get("attacking"),
            }
    except Exception as ex:
        write_log("anomalies", "get_monsters error: %s" % ex)

    return out


def pet_map():
    out = {}

    try:
        pets = get_pets() or {}

        for uid, p in pets.items():
            out[str(uid)] = {
                "uid": uid,
                "name": p.get("name"),
                "servername": p.get("servername"),
                "model": p.get("model"),
                "type": p.get("type"),
                "region": p.get("region"),
                "x": p.get("x"),
                "y": p.get("y"),
                "hp": p.get("hp"),
                "max_hp": p.get("max_hp"),
            }
    except Exception as ex:
        write_log("anomalies", "get_pets error: %s" % ex)

    return out


def char_state():
    try:
        c = get_character_data() or {}

        return {
            "name": c.get("name"),
            "job_name": c.get("job_name"),
            "level": c.get("level"),
            "hp": c.get("hp"),
            "mp": c.get("mp"),
            "max_hp": c.get("max_hp"),
            "max_mp": c.get("max_mp"),
            "region": c.get("region"),
            "x": c.get("x"),
            "y": c.get("y"),
            "z": c.get("z"),
            "locale": c.get("locale"),
        }
    except Exception as ex:
        write_log("anomalies", "get_character_data error: %s" % ex)
        return {}


# ------------------------------------------------------------
# DIFF / ANOMALY LOGIC
# ------------------------------------------------------------

def compare_character(old, new):
    if old is None:
        write_json("character", "CHAR_INITIAL", new)
        return

    changes = {}
    for k in new:
        if old.get(k) != new.get(k):
            changes[k] = {
                "before": old.get(k),
                "after": new.get(k)
            }

    if changes:
        write_json("character", "CHAR_CHANGE", changes)

        # Purely observational flags.
        if "hp" in changes:
            before = changes["hp"]["before"]
            after = changes["hp"]["after"]

            try:
                if before is not None and after is not None and int(after) <= 0:
                    write_log("anomalies", "HP reached zero or below: %s -> %s" % (before, after))
            except:
                pass


def compare_inventory(old, new, source_name):
    old_totals = item_totals(old)
    new_totals = item_totals(new)

    keys = set(old_totals.keys()) | set(new_totals.keys())

    for key in keys:
        a = old_totals.get(key, 0)
        b = new_totals.get(key, 0)

        if a == b:
            continue

        servername, model, name = key

        evt = {
            "source": source_name,
            "name": name,
            "servername": servername,
            "model": model,
            "before": a,
            "after": b,
            "delta": b - a,
        }

        write_json("inventory", "ITEM_TOTAL_CHANGE", evt)

        if b > a:
            recent_inventory_gains.append((now_float(), evt))

            # Keep only recent entries.
            cutoff = now_float() - 15.0
            while recent_inventory_gains and recent_inventory_gains[0][0] < cutoff:
                recent_inventory_gains.pop(0)


def compare_monsters(old, new):
    old_ids = set(old.keys())
    new_ids = set(new.keys())

    # Nearby entity appeared.
    for uid in sorted(new_ids - old_ids):
        m = new[uid]
        write_json("monsters", "MONSTER_APPEARED_NEARBY", m)

    # Nearby entity disappeared.
    for uid in sorted(old_ids - new_ids):
        m = old[uid]
        write_json("monsters", "MONSTER_DISAPPEARED_NEARBY", m)

    # HP / state changes.
    for uid in sorted(old_ids & new_ids):
        a = old[uid]
        b = new[uid]

        if a.get("hp") != b.get("hp"):
            evt = {
                "uid": uid,
                "name": b.get("name"),
                "servername": b.get("servername"),
                "model": b.get("model"),
                "hp_before": a.get("hp"),
                "hp_after": b.get("hp"),
                "max_hp": b.get("max_hp"),
                "region": b.get("region"),
                "x": b.get("x"),
                "y": b.get("y"),
            }
            write_json("monsters", "MONSTER_HP_CHANGE", evt)

            try:
                if int(b.get("hp", -1)) <= 0 and int(a.get("hp", 0)) > 0:
                    recent_zero_hp_monsters[uid] = (now_float(), evt)
                    write_json("anomalies", "MONSTER_HP_ZERO", evt)
            except:
                pass

    # Expire old kill candidates.
    cutoff = now_float() - 15.0
    stale = [uid for uid, (ts, _) in recent_zero_hp_monsters.items() if ts < cutoff]
    for uid in stale:
        del recent_zero_hp_monsters[uid]


def compare_pets(old, new):
    old_ids = set(old.keys())
    new_ids = set(new.keys())

    for uid in sorted(new_ids - old_ids):
        write_json("pets", "PET_APPEARED", new[uid])

    for uid in sorted(old_ids - new_ids):
        write_json("pets", "PET_DISAPPEARED", old[uid])

    for uid in sorted(old_ids & new_ids):
        a = old[uid]
        b = new[uid]

        changed = {}
        for k in ("hp", "max_hp", "region", "x", "y"):
            if a.get(k) != b.get(k):
                changed[k] = {"before": a.get(k), "after": b.get(k)}

        if changed:
            write_json("pets", "PET_CHANGE", {
                "uid": uid,
                "name": b.get("name"),
                "changes": changed
            })


def correlate_drops():
    # Correlation only; not proof of a drop.
    if not recent_zero_hp_monsters or not recent_inventory_gains:
        return

    now = now_float()

    for _, gain in list(recent_inventory_gains):
        for _, (kill_ts, monster) in list(recent_zero_hp_monsters.items()):
            delta = now - kill_ts

            if 0 <= delta <= 8.0:
                write_json("anomalies", "POSSIBLE_KILL_ITEM_CORRELATION", {
                    "seconds_after_monster_zero_hp": round(delta, 3),
                    "monster": monster,
                    "inventory_gain": gain,
                    "note": "Correlation only; pickup/reward source is not proven."
                })


# ------------------------------------------------------------
# SNAPSHOT
# ------------------------------------------------------------

def snapshot(force=False):
    global last_snapshot_at
    global last_char
    global last_inventory
    global last_job_pouch
    global last_monsters
    global last_pets

    if not running:
        return

    t = now_float()

    if not force and (t - last_snapshot_at) < SNAPSHOT_INTERVAL:
        return

    last_snapshot_at = t

    c = char_state()
    inv = inventory_map()
    pouch = pouch_map()
    mons = monster_map()
    pets = pet_map()

    compare_character(last_char, c)
    compare_inventory(last_inventory, inv, "inventory")
    compare_inventory(last_job_pouch, pouch, "job_pouch")
    compare_monsters(last_monsters, mons)
    compare_pets(last_pets, pets)

    last_char = c
    last_inventory = inv
    last_job_pouch = pouch
    last_monsters = mons
    last_pets = pets

    correlate_drops()


# ------------------------------------------------------------
# SESSION CONTROL
# ------------------------------------------------------------

def start_session():
    global running
    global session_dir
    global files
    global last_snapshot_at
    global last_char
    global last_inventory
    global last_job_pouch
    global last_monsters
    global last_pets
    global last_client_opcode_time
    global recent_zero_hp_monsters
    global recent_inventory_gains

    if running:
        log("[SPL] Session already running.")
        return

    root = os.path.join(plugin_dir(), "SilkroadPacketLogs")
    session_name = time.strftime("%Y%m%d_%H%M%S")
    session_dir = os.path.join(root, session_name)

    try:
        os.makedirs(session_dir)
    except:
        if not os.path.isdir(session_dir):
            log("[SPL] Could not create session folder.")
            return

    files = {}

    for name in (
        "packets",
        "timing",
        "character",
        "inventory",
        "monsters",
        "pets",
        "anomalies",
        "markers",
    ):
        path = os.path.join(session_dir, name + ".log")
        files[name] = open(path, "a", encoding="utf-8")

    running = True
    last_snapshot_at = 0.0
    last_char = None
    last_inventory = {}
    last_job_pouch = {}
    last_monsters = {}
    last_pets = {}
    last_client_opcode_time = {}
    recent_zero_hp_monsters = {}
    recent_inventory_gains = []

    write_log("markers", "SESSION START")
    write_log("anomalies", "Passive observation session started.")
    snapshot(True)

    log("[SPL] =======================================")
    log("[SPL] SESSION STARTED")
    log("[SPL] " + session_dir)
    log("[SPL] =======================================")


def stop_session():
    global running
    global files

    if not running:
        log("[SPL] No active session.")
        return

    snapshot(True)
    write_log("markers", "SESSION STOP")

    running = False

    for _, f in files.items():
        try:
            f.close()
        except:
            pass

    files = {}

    log("[SPL] =======================================")
    log("[SPL] SESSION STOPPED")
    log("[SPL] Logs saved in:")
    log("[SPL] " + safe(session_dir))
    log("[SPL] =======================================")


def snapshot_now():
    if not running:
        log("[SPL] Start a session first.")
        return

    snapshot(True)
    marker("MANUAL SNAPSHOT")


def mark_normal():
    marker("NORMAL STATE")


def mark_action():
    marker("TEST ACTION")


def mark_bug():
    marker("BUG OBSERVED")


def mark_note():
    try:
        note = QtBind.text(gui, txtNote).strip()
    except:
        note = ""

    if not note:
        note = "NOTE"

    marker("NOTE: " + note)


# ------------------------------------------------------------
# PACKET OBSERVATION
# ------------------------------------------------------------

def handle_silkroad(opcode, data):
    global last_client_opcode_time

    if running:
        t = now_float()

        try:
            length = len(data)
        except:
            length = -1

        write_log(
            "packets",
            "C->S OPCODE=0x%04X LEN=%d DATA=%s"
            % (opcode, length, packet_hex(data))
        )

        previous = last_client_opcode_time.get(opcode)
        last_client_opcode_time[opcode] = t

        if previous is not None:
            ms = int((t - previous) * 1000)

            write_log(
                "timing",
                "C->S OPCODE=0x%04X INTERVAL_MS=%d" % (opcode, ms)
            )

            # Generic timing signal. It does NOT infer that the packet is a skill.
            if ms <= FAST_PACKET_MS:
                write_log(
                    "anomalies",
                    "FAST_REPEATED_CLIENT_OPCODE 0x%04X interval=%dms" % (opcode, ms)
                )

        snapshot(False)

    return True


def handle_joymax(opcode, data):
    if running:
        try:
            length = len(data)
        except:
            length = -1

        write_log(
            "packets",
            "S->C OPCODE=0x%04X LEN=%d DATA=%s"
            % (opcode, length, packet_hex(data))
        )

        snapshot(False)

    return True


def teleported():
    if running:
        marker("TELEPORTED")
        snapshot(True)


def joined_game():
    if running:
        marker("JOINED GAME")
        snapshot(True)


def disconnected():
    if running:
        marker("DISCONNECTED")
        stop_session()


def finished():
    if running:
        stop_session()


log("[SPL] %s v%s loaded." % (PLUGIN_NAME, PLUGIN_VERSION))
log("[SPL] Passive logger only. It does not inject packets or automate exploits.")
