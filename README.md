# jarvis-cmd-music-assistant

Music playback and control for [Jarvis](https://github.com/alexberardi/jarvis-node-setup)
voice nodes via [Music Assistant](https://music-assistant.io/).

## What it does

```
You: "play Radiohead"
    ↓
music command  →  Music Assistant server  ──── AirPlay ────►  this node
                                                                   │
                                                                   ▼
                                                       local speaker / paired BT
```

The command talks to your Music Assistant server (over its WebSocket
API), and MA streams the audio back to the node over AirPlay. The node
receives it via `shairport-sync` (installed automatically) and routes
through the same audio stack Jarvis voice uses — so music follows any
paired Bluetooth speaker.

## Voice commands

**Play music**
- "Play Radiohead"
- "Put on some jazz"
- "Play OK Computer"
- "Queue up Bohemian Rhapsody"
- "Play Taylor Swift in the kitchen"

**Control playback**
- "Pause" / "Resume" / "Stop"
- "Skip" / "Next song" / "Go back"
- "Louder" / "Quieter" / "Set volume to 50"
- "Shuffle on" / "Shuffle off"
- "Repeat this song" / "Stop repeating"
- "Mute" / "Unmute"

## Install

Via the Jarvis mobile app: search the Pantry store for **music** and
tap install. The node will:

1. Clone this repo.
2. Static-analyze it (Pantry rules).
3. Install `shairport-sync` via the node's sudoers-gated apt helper.
4. Install `music-assistant-client` as a pip dep.
5. Start shairport-sync under your node's audio session.

Direct install paths (advanced):

```bash
python scripts/command_store.py install --url https://github.com/alexberardi/jarvis-cmd-music-assistant
# or, from a local clone:
python scripts/command_store.py install --local /path/to/jarvis-cmd-music-assistant
```

## Setup

After install, configure the three secrets in the mobile app's settings
for this command. **There's a detailed setup guide rendered inline in
the app** (it walks through the MA server, the three secrets, and the
critical AirPlay-protocol setting in MA itself). The guide content
lives in `setup_guide` in `jarvis_package.yaml` if you want to read it
from the repo.

| Secret | What it is |
|---|---|
| `MUSIC_ASSISTANT_URL` | WebSocket URL, e.g. `ws://10.0.0.50:8095/ws` |
| `MUSIC_ASSISTANT_TOKEN` | Long-lived token from MA → Settings → API tokens |
| `MUSIC_ASSISTANT_PLAYER_ID` | This node's player ID in MA (visible after install) |

### ⚠️ Heads-up: AirPlay protocol setting in MA

In MA → Settings → Players → *(this node)* → Advanced Protocol Settings,
set **"AirPlay protocol version"** to **`AirPlay 1 (RAOP)`** explicitly.

The default `Automatically select` may pick AirPlay 2 for this device,
which is silently incompatible with `shairport-sync` (MA's own docs:
*"Shairport and AirPlay 2 are currently incompatible due to lack of NTP
timing support."*) The failure mode is "playing in the web UI, no
sound from the speaker" — pin to AirPlay 1 to avoid it.

## Architecture

```
jarvis-cmd-music-assistant/
├── jarvis_package.yaml                # manifest + setup_guide
├── commands/music/command.py          # IJarvisCommand impl, no I/O of its own
└── music_assistant_shared/
    └── music_assistant_service.py     # MA WebSocket client + helpers
```

The command itself contains no subprocess calls, no apt invocations, no
direct audio paths. All it does is translate voice intent into MA API
calls. shairport-sync (the apt dependency) handles the receive-and-play
side independently as a systemd service.

## Manifest dependencies

| Type | Name | Why |
|---|---|---|
| `packages` | `music-assistant-client>=1.3.0` | MA WebSocket client |
| `apt_packages` | `shairport-sync` | AirPlay receiver — turns the node into a Music Assistant playback target |

`shairport-sync` is on the Pantry allow-list as a general-purpose
AirPlay receiver (not specific to this command). The node installs it
via its sudoers-gated `jarvis-apt-install` helper — no broad apt
privileges granted.

## Troubleshooting

See the full troubleshooting section in the mobile app's setup guide.
Quick reference:

| Symptom | First thing to check |
|---|---|
| MA shows "playing", no sound | Set MA's AirPlay protocol on this player to **AirPlay 1 (RAOP)** explicitly |
| Node not visible in MA's player list | `sudo systemctl status shairport-sync` on the node — should be `active (running)` |
| "Can't reach Music Assistant" | `MUSIC_ASSISTANT_URL` must be `ws://host:port/ws` and the token must be valid |
| Music plays from wrong speaker | Music follows pulse default sink. `pactl get-default-sink` / `pactl set-default-sink` to change |

## License

MIT — see [LICENSE](LICENSE).
