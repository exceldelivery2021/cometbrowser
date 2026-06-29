"""
YouTube Runner - Automates YouTube behavior across all archetypes
Implements: targeted/random browsing, video watching, engagement, ads, search patterns
"""

import time
import random
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from engine.platform_logic import SearchPattern, AdBehavior, SessionTracker
from .base_runner import BaseRunner


class YouTubeRunner(BaseRunner):
    """YouTube-specific automation"""
    
    def __init__(self, db=None, state_updater=None):
        super().__init__(db, state_updater)
        self.platform = "youtube"
        self.current_url = None
    
    def run(self, driver, profile_id, session_id="", targets=None):
        """Main YouTube automation entry point"""
        print(f"\n[YouTube {profile_id}] 🎬 Starting YouTube session")
        
        self.driver = driver
        self.profile_id = profile_id
        self.session_id = session_id
        self.targets = targets or []
        self.tracker = SessionTracker(profile_id)
        
        try:
            # Navigate to YouTube if not already there
            if "youtube.com" not in driver.current_url.lower():
                driver.get("https://www.youtube.com")
                time.sleep(3)
            
            # Create session and get behavior
            session = self.tracker.start_session()
            behavior = self.tracker.behavior
            
            print(f"[YouTube {profile_id}] Archetype: {behavior.archetype.value}")
            print(f"[YouTube {profile_id}] Session duration: {session['duration_minutes']}m")
            print(f"[YouTube {profile_id}] Targeted: {behavior.targeted_time_percent*100:.0f}% | Random: {behavior.random_time_percent*100:.0f}%")
            
            # Execute based on archetype
            if behavior.archetype.value == "idle":
                result = self._youtube_idle(behavior)
            elif behavior.archetype.value == "quick_jump":
                result = self._youtube_quick_jump(behavior)
            elif behavior.archetype.value == "targeted_first":
                result = self._youtube_targeted_first(behavior, session)
            else:  # random_first
                result = self._youtube_random_first(behavior, session)
            
            print(f"[YouTube {profile_id}] ✅ Session complete")
            return result
        
        except Exception as e:
            print(f"[YouTube {profile_id}] ❌ Error: {e}")
            return {"ok": False, "error": str(e), "profile_id": profile_id}
    
    def _youtube_idle(self, behavior):
        """3-5% - Stay on homepage/current video, minimal interaction"""
        print(f"[YouTube {self.profile_id}] IDLE: Staying on current page")
        
        # Just scroll a bit and wait
        self._scroll_page(random.randint(2, 5))
        time.sleep(random.randint(60, 180))
        
        return {
            "ok": True,
            "behavior": "idle",
            "profile_id": self.profile_id,
            "videos_watched": 0
        }
    
    def _youtube_quick_jump(self, behavior):
        """15-20% - Immediately jump to targeted content"""
        print(f"[YouTube {self.profile_id}] QUICK_JUMP: Jump to targeted immediately")
        
        if not self.targets:
            # No targets, just browse
            self._search_and_watch(behavior)
            return {"ok": True, "behavior": "quick_jump", "profile_id": self.profile_id, "videos_watched": 1}
        
        # Jump to first target
        target = self.targets[0]
        self._navigate_to_target(target)
        self._watch_video_with_behavior(behavior)
        
        # Maybe watch one more
        if random.random() < 0.3:
            self._watch_next_recommended(behavior)
        
        return {
            "ok": True,
            "behavior": "quick_jump",
            "profile_id": self.profile_id,
            "videos_watched": 1
        }
    
    def _youtube_targeted_first(self, behavior, session):
        """40-45% - Target first, then random wandering"""
        print(f"[YouTube {self.profile_id}] TARGETED_FIRST: Focus on targets, then wander")
        
        session_duration = session['duration_minutes'] * 60  # Convert to seconds
        targeted_time = session_duration * behavior.targeted_time_percent
        random_time = session_duration * behavior.random_time_percent
        
        videos_watched = 0
        
        # Phase 1: Targeted content (60-80% of time)
        print(f"[YouTube {self.profile_id}] Phase 1: Targeted content ({targeted_time:.0f}s)")
        videos_watched += self._browse_targeted_videos(targeted_time, behavior)
        
        # Phase 2: Random wandering (20-40% of time)
        if random_time > 0:
            print(f"[YouTube {self.profile_id}] Phase 2: Random browsing ({random_time:.0f}s)")
            videos_watched += self._browse_random_videos(random_time, behavior)
        
        return {
            "ok": True,
            "behavior": "targeted_first",
            "profile_id": self.profile_id,
            "videos_watched": videos_watched
        }
    
    def _youtube_random_first(self, behavior, session):
        """25-35% - Random browse first, then jump to targeted"""
        print(f"[YouTube {self.profile_id}] RANDOM_FIRST: Browse random, then discover targets")
        
        session_duration = session['duration_minutes'] * 60
        random_time = session_duration * behavior.random_time_percent
        targeted_time = session_duration * behavior.targeted_time_percent
        
        videos_watched = 0
        
        # Phase 1: Random browsing (appears natural)
        if random_time > 0:
            print(f"[YouTube {self.profile_id}] Phase 1: Random browsing ({random_time:.0f}s)")
            videos_watched += self._browse_random_videos(random_time, behavior)
        
        # Phase 2: Discover/jump to targeted
        print(f"[YouTube {self.profile_id}] Phase 2: Discovering targets ({targeted_time:.0f}s)")
        videos_watched += self._browse_targeted_videos(targeted_time, behavior)
        
        return {
            "ok": True,
            "behavior": "random_first",
            "profile_id": self.profile_id,
            "videos_watched": videos_watched
        }
    
    def _browse_targeted_videos(self, duration_seconds: int, behavior) -> int:
        """Browse and watch targeted channels/videos"""
        start_time = time.time()
        videos_watched = 0
        
        while time.time() - start_time < duration_seconds:
            if not self.targets:
                break
            
            target = random.choice(self.targets)
            print(f"[YouTube {self.profile_id}] 🎯 Navigating to target: {target}")
            
            self._navigate_to_target(target)
            self._watch_video_with_behavior(behavior)
            videos_watched += 1
            
            # Engagement
            self._youtube_like_if_random(behavior)
            self._youtube_subscribe_if_random(behavior)
            self._youtube_comment_if_random(behavior)
            
            # Maybe watch next
            if random.random() < 0.5:
                self._watch_next_recommended(behavior)
                videos_watched += 1
        
        return videos_watched
    
    def _browse_random_videos(self, duration_seconds: int, behavior) -> int:
        """Browse and watch random recommendations"""
        start_time = time.time()
        videos_watched = 0
        
        while time.time() - start_time < duration_seconds:
            # Use search pattern for variety
            if behavior.search_pattern == SearchPattern.SEARCH_BAR:
                self._random_search()
            elif behavior.search_pattern == SearchPattern.RECOMMENDATIONS:
                self._watch_next_recommended(behavior)
            elif behavior.search_pattern == SearchPattern.PLAYLIST:
                self._navigate_random_playlist()
            else:
                self._watch_next_recommended(behavior)
            
            self._watch_video_with_behavior(behavior)
            videos_watched += 1
        
        return videos_watched
    
    def _navigate_to_target(self, target):
        """Navigate to a specific channel or video"""
        try:
            if isinstance(target, dict):
                url = str(target.get("url") or target.get("identifier") or "").strip()
            else:
                url = str(target).strip()

            if url.startswith("http"):
                self.driver.get(url)
            else:
                self.driver.get(f"https://www.youtube.com/results?search_query={url}")
            
            self._random_delay(2, 4)
        except Exception as e:
            print(f"[YouTube {self.profile_id}] Could not navigate to {target}: {e}")
    
    def _watch_video_with_behavior(self, behavior):
        """Watch current video with realistic behavior"""
        try:
            # Wait for video to start
            time.sleep(2)
            
            # Get video duration
            try:
                duration_element = self.driver.find_element(By.CLASS_NAME, "ytp-duration")
                duration_text = duration_element.text
                # Parse duration MM:SS or HH:MM:SS
                parts = duration_text.split(":")
                if len(parts) == 2:
                    duration_seconds = int(parts[0]) * 60 + int(parts[1])
                else:
                    duration_seconds = int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
            except:
                duration_seconds = random.randint(180, 600)
            
            # Watch duration based on behavior
            watch_seconds = int(duration_seconds * behavior.watch_duration_percent)
            print(f"[YouTube {self.profile_id}] Watching for {watch_seconds}s (of {duration_seconds}s)")
            
            # Simulate watching with pauses/scrolling
            start_time = time.time()
            while time.time() - start_time < watch_seconds:
                # Random pause
                if random.random() < behavior.pause_probability:
                    pause_time = random.randint(10, 30)
                    print(f"[YouTube {self.profile_id}] Pausing for {pause_time}s")
                    time.sleep(pause_time)
                else:
                    time.sleep(random.uniform(2, 5))
                
                # Random scroll
                if random.random() < 0.2:
                    self._scroll_page(random.randint(1, 3))
            
            # Handle ads if they appear
            self._handle_youtube_ads(behavior)
            
        except Exception as e:
            print(f"[YouTube {self.profile_id}] Error watching video: {e}")
    
    def _handle_youtube_ads(self, behavior):
        """Handle YouTube ads based on profile behavior"""
        try:
            # Check for ad
            if behavior.ad_behavior == AdBehavior.SKIP_IMMEDIATELY:
                self._skip_ad_immediately()
            elif behavior.ad_behavior == AdBehavior.SKIP_AFTER_5S:
                time.sleep(5)
                self._skip_ad_if_possible()
            elif behavior.ad_behavior == AdBehavior.WATCH_FULL:
                print(f"[YouTube {self.profile_id}] Watching full ad")
                time.sleep(random.randint(15, 30))
            else:  # WATCH_PARTIAL
                print(f"[YouTube {self.profile_id}] Watching partial ad")
                time.sleep(random.randint(8, 15))
        except:
            pass
    
    def _skip_ad_immediately(self):
        """Skip ad immediately"""
        try:
            skip_button = self.driver.find_element(By.CLASS_NAME, "ytp-ad-skip-button")
            skip_button.click()
            print(f"[YouTube {self.profile_id}] Skipped ad immediately")
            time.sleep(1)
        except:
            pass
    
    def _skip_ad_if_possible(self):
        """Skip ad if skip button available"""
        try:
            skip_button = self.driver.find_element(By.CLASS_NAME, "ytp-ad-skip-button")
            skip_button.click()
            print(f"[YouTube {self.profile_id}] Skipped ad after 5s")
            time.sleep(1)
        except:
            pass
    
    def _watch_next_recommended(self, behavior):
        """Click on next recommended video"""
        try:
            # Find recommended videos
            recommended = self.driver.find_elements(By.CLASS_NAME, "yt-simple-endpoint")
            if recommended:
                video = random.choice(recommended)
                video.click()
                self._random_delay(2, 4)
                return True
        except:
            pass
        return False
    
    def _random_search(self):
        """Perform a random search"""
        try:
            # Try multiple selectors — YouTube DOM has changed over time
            search_box = None
            for selector in [
                (By.CSS_SELECTOR, "input#search"),
                (By.CSS_SELECTOR, "input[name='search_query']"),
                (By.NAME, "search_query"),
                (By.ID, "search"),
            ]:
                try:
                    search_box = self.driver.find_element(*selector)
                    if search_box.is_displayed():
                        break
                except Exception:
                    continue
            if not search_box:
                return
            search_box.clear()
            
            # Random search terms
            search_terms = [
                "technology", "music", "gaming", "vlog", "tutorial",
                "entertainment", "news", "education", "sports", "comedy"
            ]
            search_term = random.choice(search_terms)
            
            search_box.send_keys(search_term)
            search_box.send_keys(Keys.RETURN)
            self._random_delay(2, 4)
            print(f"[YouTube {self.profile_id}] Searched for: {search_term}")
        except Exception as e:
            print(f"[YouTube {self.profile_id}] Search failed: {e}")
    
    def _navigate_random_playlist(self):
        """Navigate to a random playlist"""
        try:
            playlists = [
                "https://www.youtube.com/watch?v=dQw4w9WgXcQ&list=PLrAXtmErZgOeiKm4sgNOknGvNjby9efdf",
                "https://www.youtube.com/watch?v=9bZkp7q19f0&list=PLrAXtmErZgOeiKm4sgNOknGvNjby9efdf"
            ]
            playlist = random.choice(playlists)
            self.driver.get(playlist)
            self._random_delay(2, 4)
        except:
            pass
    
    def _youtube_like_if_random(self, behavior):
        """Random chance to like video"""
        if random.random() < behavior.like_probability:
            try:
                like_button = self.driver.find_element(By.CLASS_NAME, "yt-spec-button-toggle-round")
                like_button.click()
                print(f"[YouTube {self.profile_id}] ❤️ Liked video")
                self._random_delay(1, 2)
            except:
                pass
    
    def _youtube_subscribe_if_random(self, behavior):
        """Random chance to subscribe"""
        if random.random() < behavior.subscribe_probability:
            try:
                subscribe_button = self.driver.find_element(By.CLASS_NAME, "yt-spec-button-shape-next--size-m")
                subscribe_button.click()
                print(f"[YouTube {self.profile_id}] 🔔 Subscribed to channel")
                self._random_delay(2, 3)
            except:
                pass
    
    def _youtube_comment_if_random(self, behavior):
        """Random chance to comment"""
        if random.random() < behavior.comment_probability:
            print(f"[YouTube {self.profile_id}] 💬 Would comment (not implemented for safety)")
            # Don't actually comment to avoid spam
    
    def _scroll_page(self, times: int):
        """Scroll page down"""
        for _ in range(times):
            self.driver.execute_script("window.scrollBy(0, window.innerHeight);")
            time.sleep(random.uniform(1, 2))
    
    def _search_and_watch(self, behavior):
        """Search for random content and watch"""
        self._random_search()
        try:
            videos = self.driver.find_elements(By.CLASS_NAME, "yt-simple-endpoint")
            if videos:
                videos[0].click()
                self._random_delay(2, 4)
                self._watch_video_with_behavior(behavior)
        except:
            pass
    
    def _random_delay(self, min_sec=1, max_sec=5):
        """Human-like delay"""
        time.sleep(random.uniform(min_sec, max_sec))
