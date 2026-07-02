from .base_runner import BasePlatformRunner
from .youtube_runner import YouTubeRunner
from .twitch_runner import TwitchRunner
from .spotify_runner import SpotifyRunner
from .deezer_runner import DeezerRunner


def get_runner(platform, db=None, state_updater=None):
    platform = str(platform or "").strip().lower()

    runners = {
        "youtube": YouTubeRunner,
        "twitch":  TwitchRunner,
        "spotify": SpotifyRunner,
        "deezer":  DeezerRunner,
    }

    runner_class = runners.get(platform)
    if not runner_class:
        return None

    return runner_class(db=db, state_updater=state_updater)
