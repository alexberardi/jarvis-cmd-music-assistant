"""
Music Assistant service wrapper.

Async wrapper around the official music-assistant-client package.
Provides methods for playing music, controlling playback, and managing players.
"""

from difflib import SequenceMatcher
from enum import Enum
from typing import Any, Dict, List, Optional


# Re-export enums from music_assistant_models when available
# These stubs allow the code to work even without the package installed
try:
    from music_assistant_models.enums import MediaType, QueueOption, RepeatMode
except ImportError:
    # Stub enums for when music-assistant-client is not installed

    class MediaType(str, Enum):
        """Type of media content."""
        ARTIST = "artist"
        ALBUM = "album"
        TRACK = "track"
        PLAYLIST = "playlist"
        RADIO = "radio"

    class QueueOption(str, Enum):
        """Queue insertion options."""
        PLAY = "play"  # Replace queue and play
        NEXT = "next"  # Insert after current track
        ADD = "add"    # Add to end of queue

    class RepeatMode(str, Enum):
        """Repeat mode options."""
        OFF = "off"
        ONE = "one"    # Repeat current track
        ALL = "all"    # Repeat entire queue


# Import the client when available
try:
    from music_assistant_client import MusicAssistantClient
    from music_assistant_client import login_with_token as ma_login_with_token
except ImportError:
    MusicAssistantClient = None  # type: ignore
    ma_login_with_token = None  # type: ignore


async def login_with_token(
    http_url: str,
    username: str,
    password: str,
    token_name: str = "jarvis"
) -> tuple[dict, str]:
    """
    Login to Music Assistant and get a long-lived token.

    Args:
        http_url: Music Assistant HTTP URL (e.g., "http://192.168.1.50:8095")
        username: Username
        password: Password
        token_name: Name for the token (default: "jarvis")

    Returns:
        Tuple of (user_info, token)
    """
    if ma_login_with_token is None:
        raise ImportError(
            "music-assistant-client is not installed. "
            "Install it with: pip install music-assistant-client"
        )

    user, token = await ma_login_with_token(
        http_url,
        username,
        password,
        token_name=token_name
    )
    return user, token


class MusicAssistantService:
    """
    Wrapper around official Music Assistant client.

    Provides async methods for:
    - Connecting to Music Assistant server
    - Searching and playing music
    - Controlling playback (pause, resume, skip)
    - Managing volume and shuffle/repeat
    - Getting available players

    Usage:
        service = MusicAssistantService("ws://192.168.1.50:8095/ws")
        await service.connect()
        players = await service.get_players()
        await service.search_and_play("Radiohead", players[0]["id"])
        await service.disconnect()
    """

    def __init__(self, url: str, token: Optional[str] = None):
        """
        Initialize the service.

        Args:
            url: Music Assistant WebSocket URL (e.g., "ws://192.168.1.50:8095/ws")
            token: Authentication token (required for server schema >= 28)
        """
        self.url = url
        self.token = token
        self._client: Optional[Any] = None
        self._connected = False

    @property
    def connected(self) -> bool:
        """Whether the client is connected."""
        return self._connected

    async def connect(self) -> None:
        """
        Establish connection to Music Assistant.

        Raises:
            ConnectionError: If connection fails
            AuthenticationRequired: If token is needed but not provided
        """
        if MusicAssistantClient is None:
            raise ImportError(
                "music-assistant-client is not installed. "
                "Install it with: pip install music-assistant-client"
            )

        self._client = MusicAssistantClient(self.url, None, token=self.token)
        await self._client.connect()
        # Fetch initial state to populate players list
        await self._client.players.fetch_state()
        self._connected = True

    async def disconnect(self) -> None:
        """Close connection to Music Assistant."""
        if self._client:
            await self._client.disconnect()
        self._connected = False

    # --- Players ---

    async def get_players(self) -> List[Dict[str, Any]]:
        """
        Get all available players.

        Returns:
            List of player dicts with id, name, and state
        """
        if not self._client:
            return []

        # In newer versions, players are accessed via client.players.players property
        players = self._client.players.players
        return [
            {
                "id": p.player_id,
                "name": p.name,
                "state": p.state.value if hasattr(p, 'state') and p.state else "unknown"
            }
            for p in players
        ]

    async def get_active_player(self) -> Optional[Dict[str, Any]]:
        """Return the player that is currently playing (or paused, then buffering).

        Used so voice commands like "pause" without an explicit player target
        act on whatever speaker the user is actually using, rather than a
        configured default that may be sitting idle in a different room.
        Returns None if no player is in an active state.
        """
        if not self._client:
            return None

        priority = {"playing": 0, "paused": 1, "buffering": 2}
        candidates: list[tuple[int, Any]] = []
        for p in self._client.players.players:
            state = p.state.value if hasattr(p, "state") and p.state else "unknown"
            if state in priority:
                candidates.append((priority[state], p))

        if not candidates:
            return None

        candidates.sort(key=lambda t: t[0])
        p = candidates[0][1]
        return {
            "id": p.player_id,
            "name": p.name,
            "state": p.state.value if hasattr(p, "state") and p.state else "unknown",
        }

    async def get_player_by_name(self, name: str) -> Optional[Dict[str, Any]]:
        """
        Find player by name (case-insensitive partial match).

        Args:
            name: Player name to search for

        Returns:
            Player dict if found, None otherwise
        """
        # Try built-in get_by_name first if available
        if self._client and hasattr(self._client.players, 'get_by_name'):
            try:
                player = await self._client.players.get_by_name(name)
                if player:
                    return {
                        "id": player.player_id,
                        "name": player.name,
                        "state": player.state.value if hasattr(player, 'state') and player.state else "unknown"
                    }
            except Exception as e:
                pass  # Fall back to manual search

        # Manual fuzzy search
        players = await self.get_players()
        name_lower = name.lower()
        for p in players:
            if name_lower in p["name"].lower():
                return p
        return None

    # --- Playback Controls ---

    async def pause(self, queue_id: str) -> None:
        """Pause playback on a queue."""
        if self._client:
            await self._client.player_queues.pause(queue_id)

    async def resume(self, queue_id: str) -> None:
        """Resume playback on a queue."""
        if self._client:
            await self._client.player_queues.resume(queue_id)

    async def stop(self, queue_id: str) -> None:
        """Stop playback on a queue."""
        if self._client:
            await self._client.player_queues.stop(queue_id)

    async def next_track(self, queue_id: str) -> None:
        """Skip to next track in queue."""
        if self._client:
            await self._client.player_queues.next(queue_id)

    async def previous_track(self, queue_id: str) -> None:
        """Go to previous track in queue."""
        if self._client:
            await self._client.player_queues.previous(queue_id)

    # --- Volume Controls ---

    async def set_volume(self, player_id: str, level: int) -> None:
        """
        Set volume level.

        Args:
            player_id: Player to control
            level: Volume level 0-100
        """
        if self._client:
            await self._client.players.volume_set(player_id, level)

    async def volume_up(self, player_id: str) -> None:
        """Increase volume."""
        if self._client:
            await self._client.players.volume_up(player_id)

    async def volume_down(self, player_id: str) -> None:
        """Decrease volume."""
        if self._client:
            await self._client.players.volume_down(player_id)

    # --- Shuffle and Repeat ---

    async def set_shuffle(self, queue_id: str, enabled: bool) -> None:
        """Enable or disable shuffle."""
        if self._client:
            await self._client.player_queues.shuffle(queue_id, enabled)

    async def set_repeat(self, queue_id: str, mode: RepeatMode) -> None:
        """
        Set repeat mode.

        Args:
            queue_id: Queue to control
            mode: RepeatMode.OFF, RepeatMode.ONE, or RepeatMode.ALL
        """
        if self._client:
            await self._client.player_queues.repeat(queue_id, mode)

    async def get_queue_state(self, queue_id: str) -> Optional[Dict[str, Any]]:
        """Return {shuffle_enabled, repeat_mode} for a queue, or None.

        Reads MA's in-memory cache (populated by fetch_state at connect), so
        it doesn't add a server round-trip. Used by toggle-style commands
        ("shuffle", "repeat") that need to know current state before flipping.
        """
        if not self._client:
            return None
        queue = self._client.player_queues.get(queue_id)
        if not queue:
            return None
        return {
            "shuffle_enabled": queue.shuffle_enabled,
            "repeat_mode": queue.repeat_mode,
        }

    async def set_mute(self, player_id: str, muted: bool) -> None:
        """Mute or unmute a player using MA's native mute flag.

        Preserves the underlying volume — unmute restores prior level,
        unlike volume_set(0)/volume_set(50) which would clobber it.
        """
        if self._client:
            await self._client.players.volume_mute(player_id, muted)

    # --- Search and Play ---

    async def search_for_item(
        self,
        query: str,
        media_type: Optional[MediaType] = None,
    ) -> Optional[Any]:
        """Search the MA library and return the single best-matching item.

        Returns the raw MA media item (an Artist/Album/Track/Playlist/Radio
        object) so callers can both inspect its metadata for a spoken
        response and pass it to ``play_item`` later. Returns None when MA
        finds no results across any media type.
        """
        if not self._client:
            return None

        if media_type:
            media_types = [media_type]
        else:
            media_types = [
                MediaType.TRACK,
                MediaType.ALBUM,
                MediaType.ARTIST,
                MediaType.PLAYLIST,
                MediaType.RADIO,
            ]

        results = await self._client.music.search(query, media_types, limit=10)
        return self._pick_best_result(results, media_type, query)

    async def play_item(
        self,
        queue_id: str,
        item: Any,
        queue_option: QueueOption = QueueOption.PLAY,
        radio_mode: bool = False,
    ) -> None:
        """Start playback of an item previously returned by ``search_for_item``.

        Split from ``search_and_play`` so callers can defer the play step
        until the wake-word duck has been released (see jarvis-command-sdk
        ``CommandResponse.on_response_complete``) — otherwise the first
        few seconds of audio are streamed into the duck null sink and the
        user hears the track start mid-song.
        """
        if not self._client:
            raise RuntimeError("Not connected")
        await self._client.player_queues.play_media(
            queue_id=queue_id,
            media=item,
            option=queue_option,
            radio_mode=radio_mode,
        )

    async def search_and_play(
        self,
        query: str,
        queue_id: str,
        media_type: Optional[MediaType] = None,
        queue_option: QueueOption = QueueOption.PLAY,
        radio_mode: bool = False
    ) -> Dict[str, Any]:
        """
        Search for content and play it.

        Kept for backwards-compat with callers that don't need to defer
        playback. New code that drives playback via voice should prefer the
        ``search_for_item`` + ``play_item`` split so playback can be deferred
        until the wake-word duck has been released.
        """
        if not self._client:
            return {"success": False, "error": "Not connected"}

        item = await self.search_for_item(query, media_type)
        if not item:
            return {"success": False, "error": f"No results for '{query}'"}

        await self.play_item(
            queue_id, item, queue_option=queue_option, radio_mode=radio_mode,
        )

        return {
            "success": True,
            "item": {"name": item.name, "type": item.media_type.value}
        }

    def _pick_best_result(
        self,
        results: Any,
        preferred_type: Optional[MediaType],
        query: Optional[str] = None,
    ) -> Optional[Any]:
        """Pick best search result by name-similarity to the query.

        Scores every item across all media types and returns the highest. Used
        instead of "first result wins" because MA's per-type ordering is by
        provider relevance, not cross-type — so a barely-relevant track can
        beat an exact-match artist. Exact + substring matches get a bonus;
        preferred_type gets a smaller bonus.

        Falls back to first available across types if query is empty.
        """
        q = (query or "").lower().strip()

        type_attr: list[tuple[Any, str]] = [
            (MediaType.TRACK, "tracks"),
            (MediaType.ALBUM, "albums"),
            (MediaType.ARTIST, "artists"),
            (MediaType.PLAYLIST, "playlists"),
            (MediaType.RADIO, "radio"),
        ]

        best: Any = None
        best_score: float = -1.0
        for mt, attr in type_attr:
            items = getattr(results, attr, None) or []
            for idx, item in enumerate(items):
                name = (getattr(item, "name", "") or "").lower()
                if not name:
                    continue

                sim: float = SequenceMatcher(None, q, name).ratio() if q else 0.0
                if q and name == q:
                    sim += 0.5
                elif q and (q in name or name in q):
                    sim += 0.15

                # Tiny penalty for items deeper in MA's per-type list, so
                # ties break toward MA's relevance ranking.
                score = sim - (idx * 0.02)

                if preferred_type and mt == preferred_type:
                    score += 0.3

                if score > best_score:
                    best_score = score
                    best = item

        return best
