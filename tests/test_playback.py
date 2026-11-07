"""The IJarvisMusicCommand side: what the node's display, the app and the built-in transport
commands see. Every state is read from the MA server (here, MA's own models behind a fake
connection) for this node's player."""
from __future__ import annotations

import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from music_assistant_models.enums import RepeatMode
from music_assistant_models.media_items import Track
from music_assistant_models.player_queue import PlayerQueue
from music_assistant_models.queue_item import QueueItem

from commands.music.command import MusicCommand
from music_assistant_shared.music_assistant_service import MusicAssistantService

SECRETS = {"MUSIC_ASSISTANT_URL": "ws://ma.local:8095/ws", "MUSIC_ASSISTANT_TOKEN": "tok",
           "MUSIC_ASSISTANT_PLAYER_ID": "node1"}


def _queue(state: str = "playing", *, radio: bool = False, **over) -> PlayerQueue:
    track = Track.from_dict({
        "item_id": "1", "provider": "library", "name": "Song", "provider_mappings": [],
        "artists": [{"item_id": "a", "provider": "library", "name": "A", "media_type": "artist"},
                    {"item_id": "b", "provider": "library", "name": "B", "media_type": "artist"}],
        "album": {"item_id": "c", "provider": "library", "name": "Album", "media_type": "album"},
    })
    item: dict = {"queue_id": "q1", "queue_item_id": "x", "name": "A, B - Song", "duration": 200,
                  "media_item": track.to_dict()}
    if radio:
        item.update(duration=None, media_item={"item_id": "r", "provider": "library", "name": "WXYZ",
                                               "provider_mappings": [], "media_type": "radio"},
                    streamdetails={"provider": "library", "item_id": "r", "audio_format": {},
                                   "media_type": "radio",
                                   "stream_metadata": {"title": "On Air", "artist": "Artist"}})
    q = {"queue_id": "q1", "active": True, "display_name": "Node", "available": True, "items": 3,
         "state": state, "elapsed_time": 30, "elapsed_time_last_updated": time.time() - 10,
         "current_item": QueueItem.from_dict(item).to_dict(), "repeat_mode": "all", "shuffle_enabled": False}
    q.update(over)
    return PlayerQueue.from_dict(q)


@pytest.fixture(autouse=True)
def no_settle_wait(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("commands.music.command._SETTLE_STEP_SECONDS", 0)


@pytest.fixture
def ma() -> MagicMock:
    """The MA server, as the service sees it: one connection per call."""
    svc = MagicMock(spec=MusicAssistantService)
    for name in ("connect", "disconnect", "get_active_queue", "resume", "pause", "next_track",
                 "previous_track", "seek", "set_volume", "set_shuffle", "set_repeat"):
        setattr(svc, name, AsyncMock())
    svc.get_active_queue.return_value = _queue()
    svc.get_volume = AsyncMock(return_value=40)
    svc.get_current_image = AsyncMock()
    return svc


@pytest.fixture
def cmd(ma: MagicMock) -> MusicCommand:
    with patch("commands.music.command.JarvisStorage") as storage:
        storage.return_value.get_secret.side_effect = lambda key, **_: SECRETS.get(key)
        c = MusicCommand()
    c._get_music_service = lambda: ma
    return c


def test_status_reads_this_nodes_player(cmd: MusicCommand, ma: MagicMock) -> None:
    st = cmd.playback_status()
    ma.get_active_queue.assert_awaited_with("node1")
    ma.disconnect.assert_awaited()
    assert st.to_dict() | {"position": round(st.position)} == {
        "state": "playing", "media_title": "Song", "media_artist": "A, B", "media_album": "Album",
        "context": "", "actions": ["play", "pause", "next", "previous", "shuffle", "repeat", "seek", "volume"],
        "position": 40, "duration": 200.0, "volume": 40, "shuffle": False, "repeat": "all",
    }


def test_paused_holds_its_position(cmd: MusicCommand, ma: MagicMock) -> None:
    ma.get_active_queue.return_value = _queue("paused")
    st = cmd.playback_status()
    assert (st.state, st.position) == ("paused", 30.0)


def test_radio_shows_whats_on_air(cmd: MusicCommand, ma: MagicMock) -> None:
    ma.get_active_queue.return_value = _queue(radio=True)
    ma.get_volume.return_value = None
    st = cmd.playback_status()
    assert (st.media_title, st.media_artist, st.context, st.position, st.duration) == (
        "On Air", "Artist", "WXYZ", None, None)
    assert "seek" not in st.actions and "volume" not in st.actions


@pytest.mark.parametrize("queue", [None, _queue("idle"), _queue(current_item=None)])
def test_nothing_playing(cmd: MusicCommand, ma: MagicMock, queue) -> None:
    ma.get_active_queue.return_value = queue
    assert cmd.playback_status() is None


def test_unreachable_or_unconfigured_is_nothing_playing(cmd: MusicCommand, ma: MagicMock) -> None:
    ma.connect.side_effect = OSError("refused")
    assert cmd.playback_status() is None
    with pytest.raises(OSError):
        cmd.playback_control("pause")
    SECRETS_NO_PLAYER = {**SECRETS, "MUSIC_ASSISTANT_PLAYER_ID": None}
    cmd._storage.get_secret.side_effect = lambda key, **_: SECRETS_NO_PLAYER.get(key)
    assert cmd.playback_status() is None
    with pytest.raises(RuntimeError):
        cmd.playback_control("pause")


def test_controls_go_to_the_active_queue(cmd: MusicCommand, ma: MagicMock) -> None:
    cmd.playback_control("pause")
    ma.pause.assert_awaited_with("q1")
    cmd.playback_control("play")
    ma.resume.assert_awaited_with("q1")
    cmd.playback_control("next")
    cmd.playback_control("previous")
    ma.next_track.assert_awaited_with("q1")
    ma.previous_track.assert_awaited_with("q1")
    cmd.playback_control("seek", position=90.6)
    ma.seek.assert_awaited_with("q1", 91)
    cmd.playback_control("volume", volume=140)
    ma.set_volume.assert_awaited_with("node1", 100)  # volume is the player's, not the queue's
    cmd.playback_control("shuffle")
    ma.set_shuffle.assert_awaited_with("q1", True)
    cmd.playback_control("repeat")
    ma.set_repeat.assert_awaited_with("q1", RepeatMode.ONE)  # off -> all -> one -> off
    with pytest.raises(ValueError):
        cmd.playback_control("like")


def test_control_reads_back_once_ma_applies_it(cmd: MusicCommand, ma: MagicMock) -> None:
    # The control's queue, the state before, two reads still showing "playing", then paused.
    ma.get_active_queue.side_effect = [_queue(), _queue(), _queue(), _queue(), _queue("paused")]
    assert cmd.playback_control("pause").state == "paused"
    ma.get_volume.side_effect = [40, 40, 25]
    ma.get_active_queue.side_effect = None
    assert cmd.playback_control("volume", volume=25).volume == 25


def test_seek_reads_back_the_new_position(cmd: MusicCommand, ma: MagicMock) -> None:
    # MA first extrapolates the new position from the old timestamp (here 30 + 10 s), then settles.
    stale = _queue(elapsed_time=90, elapsed_time_last_updated=time.time() - 10)
    fresh = _queue(elapsed_time=90, elapsed_time_last_updated=time.time())
    ma.get_active_queue.side_effect = [_queue(), _queue(), stale, fresh]
    assert round(cmd.playback_control("seek", position=90).position) == 90


def test_a_control_that_changes_nothing_stops_waiting(cmd: MusicCommand, ma: MagicMock) -> None:
    assert cmd.playback_control("pause").state == "playing"  # MA never paused it
    assert ma.get_active_queue.await_count == 3 + 10  # the queue, before, after, 10 re-reads


def _http_returning(content_type: str, data: bytes) -> MagicMock:
    resp = MagicMock(content_type=content_type, read=AsyncMock(return_value=data), raise_for_status=MagicMock())
    get = MagicMock()
    get.return_value.__aenter__ = AsyncMock(return_value=resp)
    get.return_value.__aexit__ = AsyncMock(return_value=False)
    session = MagicMock(get=get)
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)
    return session


IMAGE = {"type": "thumb", "path": "https://i.scdn.co/image/a b", "provider": "spotify", "remotely_accessible": True}


def test_artwork_comes_through_mas_image_proxy(cmd: MusicCommand, ma: MagicMock) -> None:
    ma.get_current_image.return_value = {**IMAGE, "proxy_id": "1f6c"}  # MA 2.10+
    session = _http_returning("image/jpeg", b"\xff\xd8jpeg")
    with patch("aiohttp.ClientSession", return_value=session):
        art = cmd.playback_artwork()
        assert cmd.playback_artwork() is art  # once per track
    assert (art.data, art.mime) == (b"\xff\xd8jpeg", "image/jpeg")
    assert session.get.call_count == 1
    assert session.get.call_args.args[0] == "http://ma.local:8095/imageproxy/1f6c?size=512"
    assert session.get.call_args.kwargs["headers"] == {"Authorization": "Bearer tok"}


def test_artwork_from_an_older_server(cmd: MusicCommand, ma: MagicMock) -> None:
    ma.get_current_image.return_value = IMAGE  # no proxy_id: the path form, double-encoded
    session = _http_returning("image/png", b"\x89PNG")
    with patch("aiohttp.ClientSession", return_value=session):
        cmd.playback_artwork()
    assert session.get.call_args.args[0] == (
        "http://ma.local:8095/imageproxy?path=https%253A//i.scdn.co/image/a%2520b&provider=spotify&size=512")


def test_no_cover(cmd: MusicCommand, ma: MagicMock) -> None:
    ma.get_current_image.return_value = None
    assert cmd.playback_artwork() is None


@pytest.mark.parametrize("url,base", [("ws://h:8095/ws", "http://h:8095"), ("wss://h/ws/", "https://h")])
def test_http_base(cmd: MusicCommand, url: str, base: str) -> None:
    cmd._storage.get_secret.side_effect = lambda key, **_: url
    assert cmd._ma_http_base() == base


def test_binary() -> None:
    with patch("commands.music.command.JarvisStorage"):
        assert MusicCommand().playback_binary == "shairport-sync"
