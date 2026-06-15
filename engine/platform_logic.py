"""
Platform Behavior Logic - Defines randomized user behavior patterns
"""

import random
import time
from enum import Enum
from dataclasses import dataclass


class ProfileArchetype(Enum):
    """Profile behavior archetypes"""
    IDLE = "idle"  # 3-5% stay on same video
    QUICK_JUMP = "quick_jump"  # 15-20% jump immediately
    TARGETED_FIRST = "targeted_first"  # 40-45% go to targeted first
    RANDOM_FIRST = "random_first"  # 25-35% browse random first


class AdBehavior(Enum):
    """How profiles handle ads"""
    SKIP_IMMEDIATELY = "skip_immediately"  # 20% - skip at 0s
    SKIP_AFTER_5S = "skip_after_5s"  # 50% - skip after 5 seconds
    WATCH_FULL = "watch_full"  # 25% - watch entire ad
    WATCH_PARTIAL = "watch_partial"  # 5% - watch half then skip


class SearchPattern(Enum):
    """How profiles find content"""
    DIRECT_URL = "direct_url"  # 10% type URL directly
    SEARCH_BAR = "search_bar"  # 50% use search bar
    RECOMMENDATIONS = "recommendations"  # 30% click recommendations
    PLAYLIST = "playlist"  # 10% use playlists


@dataclass
class BehaviorProfile:
    """Complete behavior definition for one profile"""
    profile_id: int
    archetype: ProfileArchetype
    targeted_time_percent: float  # 60-80%
    random_time_percent: float  # 20-40%
    idle_time_percent: float  # 0-10%
    watch_duration_percent: float  # How long they watch (5-95%)
    rewatch_probability: float  # 0-5% chance to rewatch
    like_probability: float  # 1-8% chance to like
    subscribe_probability: float  # 0.1-2% chance to subscribe
    comment_probability: float  # 0.05-0.5% chance to comment
    playlist_probability: float  # 0.5-3% chance to add to playlist
    ad_behavior: AdBehavior
    search_pattern: SearchPattern
    search_probability: float  # 20-60% use search
    session_duration_min: int  # Minimum session length (minutes)
    session_duration_max: int  # Maximum session length (minutes)
    videos_per_session: tuple  # (min, max) videos to watch
    return_rate: float  # 40-70% probability of returning
    days_between_returns: tuple  # (min, max) days before returning
    scroll_speed: float  # 0.5-2.0 (speed multiplier)
    pause_probability: float  # 10-30% chance to pause/idle


class BehaviorFactory:
    """Creates unique behavior for each profile"""
    
    @staticmethod
    def create_profile(profile_id: int) -> BehaviorProfile:
        """Generate a complete behavior profile"""
        random.seed(profile_id)  # Same profile = same behavior pattern
        
        # Determine archetype (which strategy this profile uses)
        roll = random.random()
        if roll < 0.04:
            archetype = ProfileArchetype.IDLE
        elif roll < 0.20:
            archetype = ProfileArchetype.QUICK_JUMP
        elif roll < 0.65:
            archetype = ProfileArchetype.TARGETED_FIRST
        else:
            archetype = ProfileArchetype.RANDOM_FIRST
        
        # Time percentages vary by archetype
        if archetype == ProfileArchetype.IDLE:
            targeted = 0.0
            random_browse = 0.0
            idle = 1.0
        else:
            targeted = random.uniform(0.60, 0.80)
            random_browse = random.uniform(0.20, 0.40)
            idle = random.uniform(0.00, 0.05)
        
        # Normalize to 100%
        total = targeted + random_browse + idle
        targeted /= total
        random_browse /= total
        idle /= total
        
        # Watch duration varies by archetype
        if archetype == ProfileArchetype.IDLE:
            watch_duration = random.uniform(0.05, 0.15)
        elif archetype == ProfileArchetype.QUICK_JUMP:
            watch_duration = random.uniform(0.20, 0.50)
        else:
            watch_duration = random.uniform(0.40, 0.95)
        
        # Engagement scales with watch duration (longer watches = more engagement)
        engagement_scale = watch_duration
        
        # Ad behavior distribution
        ad_roll = random.random()
        if ad_roll < 0.20:
            ad_behavior = AdBehavior.SKIP_IMMEDIATELY
        elif ad_roll < 0.70:
            ad_behavior = AdBehavior.SKIP_AFTER_5S
        elif ad_roll < 0.95:
            ad_behavior = AdBehavior.WATCH_FULL
        else:
            ad_behavior = AdBehavior.WATCH_PARTIAL
        
        # Search pattern distribution
        search_roll = random.random()
        if search_roll < 0.12:
            search_pattern = SearchPattern.DIRECT_URL
        elif search_roll < 0.52:
            search_pattern = SearchPattern.SEARCH_BAR
        elif search_roll < 0.82:
            search_pattern = SearchPattern.RECOMMENDATIONS
        else:
            search_pattern = SearchPattern.PLAYLIST
        
        # Session patterns
        session_duration = random.randint(5, 45)
        
        return BehaviorProfile(
            profile_id=profile_id,
            archetype=archetype,
            targeted_time_percent=targeted,
            random_time_percent=random_browse,
            idle_time_percent=idle,
            watch_duration_percent=watch_duration,
            rewatch_probability=random.uniform(0.00, 0.05),
            like_probability=min(random.uniform(0.01, 0.08) * engagement_scale, 0.15),
            subscribe_probability=min(random.uniform(0.001, 0.02) * engagement_scale, 0.05),
            comment_probability=min(random.uniform(0.0005, 0.005) * engagement_scale, 0.01),
            playlist_probability=min(random.uniform(0.005, 0.03) * engagement_scale, 0.10),
            ad_behavior=ad_behavior,
            search_pattern=search_pattern,
            search_probability=random.uniform(0.20, 0.60),
            session_duration_min=max(2, session_duration - 10),
            session_duration_max=session_duration + 15,
            videos_per_session=(random.randint(2, 5), random.randint(8, 15)),
            return_rate=random.uniform(0.40, 0.70),
            days_between_returns=(random.randint(1, 3), random.randint(5, 14)),
            scroll_speed=random.uniform(0.5, 2.0),
            pause_probability=random.uniform(0.10, 0.30)
        )


class SessionTracker:
    """Tracks a profile's session history for realistic returns"""
    
    def __init__(self, profile_id: int):
        self.profile_id = profile_id
        self.behavior = BehaviorFactory.create_profile(profile_id)
        self.last_session_time = None
        self.session_count = 0
        self.total_watch_time = 0
        self.last_content_watched = None
    
    def should_return_today(self) -> bool:
        """Check if profile should return based on behavior"""
        if self.last_session_time is None:
            return True  # First session always happens
        
        days_since = (time.time() - self.last_session_time) / 86400
        min_days, max_days = self.behavior.days_between_returns
        
        if days_since < min_days:
            return False
        if days_since > max_days:
            return True
        
        # Random chance within the window
        return random.random() < self.behavior.return_rate
    
    def start_session(self) -> dict:
        """Start a new session"""
        self.session_count += 1
        self.last_session_time = time.time()
        
        duration = random.randint(
            self.behavior.session_duration_min,
            self.behavior.session_duration_max
        )
        
        videos = random.randint(
            self.behavior.videos_per_session[0],
            self.behavior.videos_per_session[1]
        )
        
        return {
            "session_id": f"{self.profile_id}_{self.session_count}_{int(time.time())}",
            "duration_minutes": duration,
            "target_videos": videos,
            "archetype": self.behavior.archetype.value,
            "behavior": self.behavior
        }