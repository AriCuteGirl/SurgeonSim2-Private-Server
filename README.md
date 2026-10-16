# Surgeon Simulator 2 — Private Server by Ari 🩺💗

Co-op for **Surgeon Simulator 2** is back. Bossa shut down the online servers and replaced the game with a
single-player-only build, so this project brings back the backend the last co-op build talks to:
a small server emulator plus an installer that points your own copy of the game at it.

**No game files are included.** You need your own copy of the last co-op build,
**1.5.1.561** (Steam depot `774793`, manifest `7262676543609055679`).

## Downloads

Grab them from [**Releases**](../../releases/latest):

| File | For | What's inside |
| --- | --- | --- |
| `SS2Revival-Windows.zip` | Players on **Windows** | `SS2Revival-Installer.exe`, `RevivalMod.dll`, PupBerg `steam_api64.dll` |
| `SS2Revival-Linux.tar.gz` | Players on **Linux / Steam Deck** | Linux installer, `RevivalMod.dll`, PupBerg, `play.sh` (Proton launcher) |
| `SS2Revival-Server.zip` | People who want to **host a server** | The Python server, VPS deploy + backup scripts, smoke test |

Players need a server address from whoever hosts one. The downloads contain no server address and no game files.

## What works

- Login through the [PupBerg](https://github.com/AriCuteGirl/PupBerg) Steam emulator (Steam doesn't need to run)
- Parties, party invites, joining a friend, peer-to-peer play with a relay fallback (no port forwarding for players)
- Quick-play matchmaking (fills with whoever is queued after 10 s)
- Profiles, friends (everyone on the server is your friend), XP
- **Daily challenges**: 3 per player per day, progress and XP saved on the server
- The campaign (it ships with the game)
- Extras: a pink **PRIVATE SERVER BY ARI** banner, silly loading texts
  ("Cracking femboys", "Patting good kitty", "Loading infinite nukes", …) and a custom news feed

Not revived: community levels (UGC), leaderboards, Twitch integration and Vivox voice chat (use Discord).

---

## Playing

You need the address of a server (ask whoever hosts it, or [host one yourself](#host-a-server)).
Everybody who wants to play together must use the same server and the same PupBerg room code.

### Windows

1. Download `SS2Revival-Windows.zip` from [Releases](../../releases).
2. Unzip it **into your old Surgeon Simulator 2 folder** (next to `Surgeon Simulator 2.exe`).
3. Double-click `SS2Revival-Installer.exe`. It asks for:
   - the **server address** (skipped if the host gave you a zip with a `server.txt` inside),
   - **who you are**: it lists the Steam accounts that logged in on your PC (like PupBerg's account picker),
     so you play with your Steam name; or type any name,
   - the **PupBerg room code** (default `SS2-REVIVAL`; use the same one as your friends).
4. Start `Surgeon Simulator 2.exe`. In the lobby, invite your friend from the party menu,
   or join them from the PupBerg overlay (**Shift+Tab**).

Undo everything: run `SS2Revival-Installer.exe uninstall` in a terminal. The originals are kept as
`Assembly-CSharp.dll.original` and `steam_api64.dll.valve_original`.

### Linux / Steam Deck

```bash
tar -xzf SS2Revival-Linux.tar.gz -C "/path/to/Surgeon Sim 2 Old"
cd "/path/to/Surgeon Sim 2 Old"
./SS2Revival-Installer install . --host SERVER-ADDRESS
./play.sh .
```

`play.sh` runs the game through Proton from your Steam install (Steam doesn't need to be running).

### Installer options

```
SS2Revival-Installer install [gameDir] [--host H] [--port 8090] [--name N] [--room R] [--pupberg-lobby H:P] [--yes]
SS2Revival-Installer uninstall [gameDir]
```

Running `install` again is safe: it always patches from the untouched original and keeps your PupBerg identity.

---

## Host a server

The server is plain **Python 3** with no extra packages (`server/`). It needs these ports open:

| Port | Protocol | What |
| --- | --- | --- |
| 8090 | TCP | REST API (login, parties, matchmaking, challenges, news) |
| 8021 | UDP | address discovery (STUN) |
| 8022 | UDP | relay for players who can't connect directly |
| 8023 | UDP | push notifications (invites, party changes) |

### On your own PC

```bash
python3 server/ss2server.py                 # Windows: py server\ss2server.py
```

- Player data is saved in `server/data/` (`--data <folder>` to change it).
- Allow the ports above in your firewall. For players outside your home network, forward them in your router
  to your PC and give friends your public IP.
- Players install with `--host <your IP>` (LAN IP for people on your Wi-Fi, public IP for everyone else).
- Check it from another machine: `python3 tests/smoke_test.py <your IP>` should end with `ALL OK`.

### On a VPS / Oracle Cloud free tier (Ubuntu or Debian)

The deploy script sets everything up from your PC over SSH.

1. Create the VM and allow the ports in your provider's firewall. On Oracle Cloud: open the VM's subnet,
   **Security List → Add Ingress Rules**, source CIDR `0.0.0.0/0`:
   - IP protocol **TCP**, destination port `8090`
   - IP protocol **UDP**, destination port range `8021-8023`
2. Copy `deploy/deploy.env.example` to `deploy/deploy.env` and fill in your VM's `user@ip` and SSH key.
   `deploy.env` is in `.gitignore`, so your server details never end up in git.
3. Run:

   ```bash
   bash deploy/deploy_oracle.sh
   ```

   It copies the server, installs it as a `systemd` service called `ss2` (it starts again after a reboot),
   opens the ports in the VM's own firewall, and at the end checks HTTP and UDP from your PC.
   Run it again to update; player data is kept.
4. Back up player data with `bash deploy/backup.sh` (goes to `backups/`, also ignored by git).

Useful on the VM: `systemctl status ss2`, `journalctl -u ss2 -f`, `sudo systemctl restart ss2`.

### Giving your friends a ready-made download

```bash
GAME_MANAGED="/path/Surgeon Simulator 2_Data/Managed" tools/package.sh
```

This builds the public downloads in `dist/`. If `deploy/deploy.env` exists (or `SS2_SERVER=<ip>` is set), it
also builds `dist/private/SS2Revival-*-<ip>` with a `server.txt` inside, so the installer doesn't have to ask.
Send those to your friends directly and **don't upload them** if you want to keep your server address private.
`dist/` is ignored by git.

### Security

- Every request except login, health, version and news needs a valid session. Sessions expire after 7 days
  without the game refreshing them and are stored in `data/sessions.json` (mode 600).
- Players can only change their own profile, challenges and invites. Party settings are leader-only, and
  matchmaking only takes your own party.
- The UDP relay only forwards between players in the same party or match, and only from the sender's
  registered address. It can't be used as an open relay.
- Request bodies are capped at 256 KB with a 20 s timeout. Login requests and tokens are never written to the log.
- The `systemd` service is sandboxed (read-only system, can only write its data folder, no new privileges).
- There are no passwords. Anyone who can reach the server can make an account with any made-up Steam ID, like on
  any Goldberg/PupBerg server. Only share the address with people you want to play with.

### Problems

| Problem | Fix |
| --- | --- |
| Installer: `this is not the 1.5.1.561 Assembly-CSharp.dll` | Wrong game version. You need the last co-op build 1.5.1.561. |
| Game stays on "Loading [100 %]" | The server isn't reachable. Open `http://SERVER:8090/auth/healthcheck` in a browser; it should say `OK`. |
| You see each other in the party but can't play together | UDP 8021-8023 is blocked. Open it in both the cloud firewall and the VM firewall (the deploy script does the VM part). |
| The friend list is empty | Both players must use the same server. Everyone on a server is everyone's friend. |

---

## How it works

| Part | What it does |
| --- | --- |
| `tools/Installer` | Patches **your** `Assembly-CSharp.dll` with Mono.Cecil: the Prod server addresses → the revival server, `https` → `http`, and hooks in `RevivalMod.dll`. Installs PupBerg's `steam_api64.dll` + `steam_settings`. |
| `tools/RevivalMod` | Tiny in-game helper: the banner and the joke loading texts (hooked into `LocalizationService.GetText`). Compiled against the game's own Mono assemblies, so building it needs your copy of the game. |
| `server/` | REST on TCP 8090; UDP 8021 STUN (`SP`), 8022 relay (`TP`/`TD`), 8023 notifications (`NP`→`ND`). Response shapes come from the client's own parsers. `challenges.py` has the daily challenge pool. |
| `deploy/` | VPS deploy (systemd, firewall) and backup scripts. |
| `tests/smoke_test.py` | Logs in two fake players, makes a party, relays a packet and checks that outsiders are refused. |

## Credits

- Server emulator, installer and RevivalMod: Ari (with Claude)
- [PupBerg](https://github.com/AriCuteGirl/PupBerg), a fork of [gbe_fork](https://github.com/Detanup01/gbe_fork) (Goldberg Steam Emulator), LGPL-3.0
- [Mono.Cecil](https://github.com/jbevain/cecil), MIT

Surgeon Simulator 2 is © Bossa Studios. This is an unofficial fan project for people who own the game;
it contains no game code or assets.
