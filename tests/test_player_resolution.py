"""Default-player resolution and play-success semantics (item #432).

The MUSIC_ASSISTANT_PLAYER_ID setting used to go to MA as-is. A MAC like
7F:66:71:2C:D2:15 is not an MA player id (AirPlay ids are ``ap`` + the
lowercase hex), so play failed in the deferred callback while the command
had already reported success.
"""

import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from commands.music.command import MusicCommand  # noqa: E402
from music_assistant_shared.music_assistant_service import (  # noqa: E402
    MusicAssistantService,
)


def _player(player_id: str, name: str, available: bool = True, state: str = "idle") -> Any:
    return SimpleNamespace(
        player_id=player_id,
        name=name,
        available=available,
        state=SimpleNamespace(value=state),
    )


PI = _player("ap7f66712cd215", "Jarvis-pi4")
KITCHEN = _player("sonos_RINCON_1234", "Kitchen")


def _service(players: List[Any]) -> MusicAssistantService:
    svc = MusicAssistantService("ws://ma.test/ws")
    client = MagicMock()
    client.players.players = players
    # No built-in get_by_name: exercise the package's own matching.
    del client.players.get_by_name
    client.player_queues.play_media = AsyncMock()
    client.player_queues.stop = AsyncMock()
    svc._client = client
    svc._connected = True
    return svc


class _FakeStorage:
    def __init__(self, secrets: Dict[str, str]) -> None:
        self._secrets = secrets

    def get_secret(self, key: str, *a: Any, **kw: Any) -> Optional[str]:
        return self._secrets.get(key)


def _command(svc: MusicAssistantService, default: Optional[str]) -> MusicCommand:
    cmd = MusicCommand()
    secrets = {"MUSIC_ASSISTANT_URL": "ws://ma.test/ws"}
    if default is not None:
        secrets["MUSIC_ASSISTANT_PLAYER_ID"] = default
    cmd._storage = _FakeStorage(secrets)  # type: ignore[assignment]
    svc.connect = AsyncMock()  # type: ignore[method-assign]
    svc.disconnect = AsyncMock()  # type: ignore[method-assign]
    svc.search_for_item = AsyncMock(  # type: ignore[method-assign]
        return_value=SimpleNamespace(name="Song", media_type=SimpleNamespace(value="track")),
    )
    cmd._get_music_service = lambda: svc  # type: ignore[method-assign]
    return cmd


# --- MusicAssistantService.resolve_player ---------------------------------


@pytest.mark.parametrize("ref", [
    "7F:66:71:2C:D2:15",
    "7f-66-71-2c-d2-15",
    "7F66712CD215",
])
def test_mac_resolves_to_airplay_id(ref: str) -> None:
    svc = _service([KITCHEN, PI])
    player = asyncio.run(svc.resolve_player(ref))
    assert player is not None
    assert player["id"] == "ap7f66712cd215"


def test_exact_id_resolves() -> None:
    svc = _service([KITCHEN, PI])
    assert asyncio.run(svc.resolve_player("sonos_RINCON_1234"))["id"] == "sonos_RINCON_1234"


def test_name_resolves_case_insensitive() -> None:
    svc = _service([KITCHEN, PI])
    assert asyncio.run(svc.resolve_player("jarvis-PI4"))["id"] == "ap7f66712cd215"


def test_exact_name_beats_partial() -> None:
    svc = _service([_player("a1", "Kitchen Speaker"), _player("a2", "Kitchen")])
    assert asyncio.run(svc.resolve_player("kitchen"))["id"] == "a2"


def test_unknown_resolves_to_none() -> None:
    svc = _service([KITCHEN, PI])
    assert asyncio.run(svc.resolve_player("aa:bb:cc:dd:ee:ff")) is None


def test_resolved_player_reports_availability() -> None:
    svc = _service([_player("ap1", "Off", available=False)])
    assert asyncio.run(svc.resolve_player("ap1"))["available"] is False


# --- play ------------------------------------------------------------------


def test_play_with_mac_default_targets_airplay_id() -> None:
    svc = _service([KITCHEN, PI])
    cmd = _command(svc, "7F:66:71:2C:D2:15")

    resp = cmd._run_play(MagicMock(), query="song")

    assert resp.success is True
    assert resp.context_data["player_id"] == "ap7f66712cd215"
    resp.on_response_complete()
    svc._client.player_queues.play_media.assert_awaited_once()
    assert svc._client.player_queues.play_media.await_args.kwargs["queue_id"] == "ap7f66712cd215"


def test_play_with_unknown_default_fails_and_names_players() -> None:
    svc = _service([KITCHEN, PI])
    cmd = _command(svc, "aa:bb:cc:dd:ee:ff")

    resp = cmd._run_play(MagicMock(), query="song")

    assert resp.success is False
    assert resp.context_data["error"] == "default_player_not_found"
    assert "Kitchen" in resp.error_details and "Jarvis-pi4" in resp.error_details
    assert resp.on_response_complete is None
    svc._client.player_queues.play_media.assert_not_called()


def test_play_on_unavailable_player_fails() -> None:
    svc = _service([_player("ap7f66712cd215", "Jarvis-pi4", available=False)])
    cmd = _command(svc, "ap7f66712cd215")

    resp = cmd._run_play(MagicMock(), query="song")

    assert resp.success is False
    assert resp.context_data["error"] == "player_unavailable"
    assert resp.on_response_complete is None


# --- control -----------------------------------------------------------------


def test_stop_with_mac_default_uses_airplay_id() -> None:
    svc = _service([KITCHEN, PI])
    cmd = _command(svc, "7F:66:71:2C:D2:15")

    resp = cmd._run_control(MagicMock(), "stop")

    assert resp.success is True
    svc._client.player_queues.stop.assert_awaited_once_with("ap7f66712cd215")


def test_stop_with_unknown_default_fails() -> None:
    svc = _service([KITCHEN])
    cmd = _command(svc, "7F:66:71:2C:D2:15")

    resp = cmd._run_control(MagicMock(), "stop")

    assert resp.success is False
    assert resp.context_data["error"] == "default_player_not_found"
    svc._client.player_queues.stop.assert_not_called()
