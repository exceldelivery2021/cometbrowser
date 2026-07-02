"""
Platform Runners Factory
Maps platform names to their runner instances.
"""

from engine.youtube_runner import YouTubeRunner
from engine.twitch_runner  import TwitchRunner
from engine.spotify_runner import SpotifyRunner
from engine.deezer_runner  import DeezerRunner

_RUNNERS = {
    "youtube": YouTubeRunner,
    "twitch":  TwitchRunner,
    "spotify": SpotifyRunner,
    "deezer":  DeezerRunner,
}


def get_runner(platform, db=None, state_updater=None):
    """
    Return the correct runner for the given platform, or None if unknown.

    Args:
        platform (str): 'youtube' | 'twitch' | 'spotify' | 'deezer'
        db: DatabaseManager instance
        state_updater: Callback to update profile state in the dashboard
    """
    platform = str(platform or "").strip().lower()
    runner_class = _RUNNERS.get(platform)
    if not runner_class:
        return None
    return runner_class(db=db, state_updater=state_updater)
