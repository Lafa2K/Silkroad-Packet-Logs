# Silkroad Packet Logs

Passive packet and state logger for phBot.

Silkroad Packet Logs helps you record what happens around your character while you test game actions: NPC dialogs, item buy/sell, teleports, inventory changes, nearby monsters, pets, combat state, and client/server packets.

It does not inject packets, automate exploits, or modify gameplay. It only observes and writes logs.

## What It Generates

When you press `START SESSION`, the plugin creates a folder:

```text
Plugins/SilkroadPacketLogs/YYYYMMDD_HHMMSS/
```

Inside it, each session contains:

```text
packets.log     C->S and S->C packet previews
timing.log      repeated client opcode timing
character.log   position, HP/MP, region, level changes
inventory.log   inventory and job pouch item changes
monsters.log    nearby monster appear/disappear/HP changes
pets.log        nearby pet changes
anomalies.log   useful hints and correlations
markers.log     manual markers added during testing
```

## Buttons

```text
START SESSION   Start recording
STOP SESSION    Stop and close the log files
SNAPSHOT NOW    Force a character/inventory/monster snapshot
MARK NORMAL     Mark a known normal state
MARK ACTION     Mark the exact moment you perform a test action
MARK BUG        Mark the moment a bug or strange result happens
MARK NOTE       Write your own note from the text box
```

Use markers often. They make the logs much easier to read later.

## Mini Tutorial: Capturing an NPC Dialog

1. Press `START SESSION`.
2. Walk near the NPC.
3. Press `MARK NORMAL`.
4. Click the NPC.
5. Press `MARK ACTION`.
6. Choose the dialog option, quest option, OK, Reward, or close button you want to capture.
7. Press `STOP SESSION`.

Useful files:

```text
packets.log
markers.log
character.log
```

Look around the `MARK ACTION` timestamp in `markers.log`, then compare it with nearby C->S lines in `packets.log`.

Example:

```text
C->S OPCODE=0x7045 LEN=4 DATA=9A010000
C->S OPCODE=0x7046 LEN=5 DATA=9A01000002
C->S OPCODE=0x30D4 LEN=1 DATA=05
```

That usually means:

```text
0x7045 = select NPC/object
0x7046 = open NPC/object
0x30D4 = choose dialog option / confirm
```

The exact meaning depends on the server and game build. Treat captures as evidence, not universal truth.

## Mini Tutorial: Capturing Buy or Sell

1. Press `START SESSION`.
2. Open the shop NPC normally.
3. Press `MARK ACTION` right before buying or selling.
4. Buy one cheap item, sell one cheap item, or repair one item.
5. Press `SNAPSHOT NOW`.
6. Press `STOP SESSION`.

Useful files:

```text
packets.log
inventory.log
markers.log
```

In `inventory.log`, look for:

```text
ITEM_TOTAL_CHANGE
```

Then match that timestamp with nearby packets. If an item quantity increased, the action was probably a buy, reward, pickup, or pouch transfer. The probe reports correlation only; it does not pretend to know the source with certainty.

## Mini Tutorial: Capturing Combat

1. Press `START SESSION`.
2. Stand near the monster.
3. Press `MARK NORMAL`.
4. Start attacking.
5. Press `MARK ACTION`.
6. Kill the monster or wait for the behavior you want to capture.
7. Press `SNAPSHOT NOW`.
8. Press `STOP SESSION`.

Useful files:

```text
monsters.log
packets.log
inventory.log
anomalies.log
```

In `monsters.log`, look for:

```text
MONSTER_APPEARED_NEARBY
MONSTER_HP_CHANGE
MONSTER_DISAPPEARED_NEARBY
```

In `anomalies.log`, the probe may write:

```text
MONSTER_HP_ZERO
POSSIBLE_KILL_ITEM_CORRELATION
```

This is useful when building tools that need to understand quest monsters, drop timing, summon behavior, or combat failure cases.

## Reading Little Endian

Silkroad packets often store numbers in little endian. That means the lowest byte comes first.

Example:

```text
DATA=9A010000
```

Split into bytes:

```text
9A 01 00 00
```

Reverse them to read the normal hex value:

```text
00 00 01 9A
```

Now convert:

```text
0x019A = 410
```

So `9A010000` is the integer `410`.

Another example:

```text
DATA=5A010000
```

Bytes:

```text
5A 01 00 00
```

Reverse:

```text
00 00 01 5A
```

Result:

```text
0x015A = 346
```

So `5A010000` is quest ID `346`.

For 2-byte values:

```text
DATA=0B00
```

Bytes:

```text
0B 00
```

Reverse:

```text
00 0B
```

Result:

```text
0x000B = 11
```

## How To Use Captures To Build Tools

A good capture usually has three pieces:

```text
1. A marker saying what you clicked or tested
2. Nearby C->S packets showing what the client sent
3. State changes proving the result: inventory, quest, monster HP, teleport, etc.
```

For example, to automate a quest dialog safely:

```text
MARK ACTION: clicked quest reward
C->S packet appears near the marker
inventory/quest state changes after it
```

Only after that should another plugin reuse the packet/action.

## Release 1.0 Scope

This version is intentionally small:

```text
Passive logging
Manual markers
Packet previews
Character/inventory/monster/pet snapshots
Simple anomaly hints
No packet injection
No exploit automation
```

Future versions can add filters, capture presets, export summaries, opcode labels, or a session viewer. Those are useful, but they are not required for a clean first release.
