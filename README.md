# jarvis-cmd-music

Music playback and control for [Jarvis](https://github.com/alexberardi/jarvis-node-setup) via [Music Assistant](https://music-assistant.io/).

## Install

```bash
python scripts/command_store.py install --url https://github.com/alexberardi/jarvis-cmd-music
```

## Setup

Run `init_data()` to configure the Music Assistant URL and auth token:
```bash
python scripts/install_command.py music
```

## Voice Commands

**Play music:**
- "Play Radiohead"
- "Put on some jazz"
- "Play OK Computer"
- "Queue up Bohemian Rhapsody"
- "Play Taylor Swift in the kitchen"

**Control playback:**
- "Pause" / "Resume" / "Stop"
- "Skip" / "Next song" / "Go back"
- "Louder" / "Quieter" / "Set volume to 50"
- "Shuffle on" / "Shuffle off"
- "Repeat this song" / "Stop repeating"
- "Mute" / "Unmute"

## Secrets

| Key | Description |
|-----|-------------|
| `MUSIC_ASSISTANT_URL` | WebSocket URL (e.g., `ws://192.168.1.50:8095/ws`) |
| `MUSIC_ASSISTANT_TOKEN` | Auth token from Music Assistant |
| `MUSIC_ASSISTANT_PLAYER_ID` | Default player ID (MAC address) |

## Structure

```
commands/music/command.py           # Voice command interface
lib/music_assistant_service.py      # Music Assistant client wrapper
```
