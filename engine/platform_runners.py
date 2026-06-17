"""
Platform Runners Factory
Maps platform names to their runner instances.
"""


def get_runner(platform, db=None, state_updater=None):
    """
    Return the correct runner for the given platform.

    Args:
        platform (str): Platform name ('youtube', 'twitch', 'spotify', 'deezer')
        db: DatabaseManager instance
        state_updater: Callback to update profile state in the dashboard

    Returns:
        BaseRunner subclass instance, or None if platform has no runner
    """
    platform = str(platform or "").strip().lower()

    if platform == "youtube":
        from engine.youtube_runner import YouTubeRunner
        return YouTubeRunner(db=db, state_updater=state_updater)

    if platform == "twitch":
        try:
            from engine.twitch_runner import TwitchRunner
            return TwitchRunner(db=db, state_updater=state_updater)
        except ImportError:
            pass

    if platform == "spotify":
        try:
            from engine.spotify_runner import SpotifyRunner
            return SpotifyRunner(db=db, state_updater=state_updater)
        except ImportError:
            pass

    if platform == "deezer":
        try:
            from engine.deezer_runner import DeezerRunner
            return DeezerRunner(db=db, state_updater=state_updater)
        except ImportError:
            pass

    return None
