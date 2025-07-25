import asyncio
import time
import threading
from datetime import datetime, timedelta
from typing import Dict, Optional, Callable
from dataclasses import dataclass
import pygame
from plyer import notification
import uuid

@dataclass
class Timer:
    """Represents a single timer instance"""
    id: str
    name: str
    duration: int  # in seconds
    remaining: int
    start_time: float
    paused_time: float = 0.0
    is_paused: bool = False
    is_completed: bool = False
    is_stopped: bool = False

class TimerManager:
    """Manages multiple concurrent cooking timers"""
    
    def __init__(self):
        self.active_timers: Dict[str, Timer] = {}
        self.timer_threads: Dict[str, threading.Thread] = {}
        self.callbacks: Dict[str, Callable] = {}
        
        # Initialize pygame for audio alerts
        try:
            pygame.mixer.init()
            self.audio_enabled = True
        except pygame.error:
            print("Warning: Audio system not available")
            self.audio_enabled = False
    
    def create_timer(self, name: str, duration: int, callback: Optional[Callable] = None) -> str:
        """
        Create a new timer
        Args:
            name: e.g. "Pasta cooking"
            duration: Timer duration (seconds)
            callback: Optional function to call when timer completes
        Returns:
            timer_id: Unique id for the timer
        """
        timer_id = str(uuid.uuid4())[:8]  # Short unique ID
        
        timer = Timer(
            id=timer_id,
            name=name,
            duration=duration,
            remaining=duration,
            start_time=0
        )
        
        self.active_timers[timer_id] = timer
        if callback:
            self.callbacks[timer_id] = callback
            
        return timer_id
    
    def start_timer(self, timer_id: str) -> bool:
        """Start a created timer"""
        if timer_id not in self.active_timers:
            return False
            
        timer = self.active_timers[timer_id]
        if timer.is_completed or timer.is_stopped:
            return False
            
        timer.start_time = time.time()
        timer.is_paused = False
        
        # Start timer thread
        timer_thread = threading.Thread(
            target=self._run_timer,
            args=(timer_id,),
            daemon=True
        )
        self.timer_threads[timer_id] = timer_thread
        timer_thread.start()
        
        print(f"⏰ Timer '{timer.name}' started for {timer.duration} seconds")
        return True
    
    def pause_timer(self, timer_id: str) -> bool:
        """Pause a running timer"""
        if timer_id not in self.active_timers:
            return False
            
        timer = self.active_timers[timer_id]
        if timer.is_paused or timer.is_completed:
            return False
            
        timer.is_paused = True
        timer.paused_time = time.time()
        print(f"⏸️ Timer '{timer.name}' paused")
        return True
    
    def resume_timer(self, timer_id: str) -> bool:
        """Resume a paused timer"""
        if timer_id not in self.active_timers:
            return False
            
        timer = self.active_timers[timer_id]
        if not timer.is_paused:
            return False
            
        # Adjust start time to account for paused duration
        pause_duration = time.time() - timer.paused_time
        timer.start_time += pause_duration
        timer.is_paused = False
        timer.paused_time = 0.0
        
        print(f"▶️ Timer '{timer.name}' resumed")
        return True
    
    def stop_timer(self, timer_id: str) -> bool:
        """Stop and remove a timer"""
        if timer_id not in self.active_timers:
            return False
            
        timer = self.active_timers[timer_id]
        timer.is_stopped = True
        
        print(f"⏹️ Timer '{timer.name}' stopped")
        return True
    
    def get_timer_status(self, timer_id: str) -> Optional[Dict]:
        """Get current status of a timer"""
        if timer_id not in self.active_timers:
            return None
            
        timer = self.active_timers[timer_id]
        
        if timer.is_completed:
            remaining = 0
        elif timer.is_paused:
            elapsed = timer.paused_time - timer.start_time
            remaining = max(0, timer.duration - elapsed)
        else:
            elapsed = time.time() - timer.start_time
            remaining = max(0, timer.duration - elapsed)
        
        return {
            'id': timer.id,
            'name': timer.name,
            'duration': timer.duration,
            'remaining': int(remaining),
            'elapsed': timer.duration - remaining,
            'is_paused': timer.is_paused,
            'is_completed': timer.is_completed,
            'is_stopped': timer.is_stopped,
            'percentage_complete': ((timer.duration - remaining) / timer.duration) * 100
        }
    
    def list_active_timers(self) -> Dict[str, Dict]:
        """Get status of all active timers"""
        return {
            timer_id: self.get_timer_status(timer_id)
            for timer_id in self.active_timers
            if not self.active_timers[timer_id].is_stopped
        }
    
    def _run_timer(self, timer_id: str):
        """Internal method to run timer countdown"""
        timer = self.active_timers[timer_id]
        
        while not timer.is_stopped:
            if timer.is_paused:
                time.sleep(0.1)
                continue
                
            elapsed = time.time() - timer.start_time
            remaining = timer.duration - elapsed
            
            if remaining <= 0:
                timer.is_completed = True
                self._timer_completed(timer_id)
                break
                
            time.sleep(0.1)
    
    def _timer_completed(self, timer_id: str):
        """Handle timer completion"""
        timer = self.active_timers[timer_id]
        
        print(f"🔔 Timer '{timer.name}' completed!")
        
        # Show system notification
        try:
            notification.notify(
                title="Super Spoon Timer",
                message=f"Timer '{timer.name}' has finished!",
                timeout=10
            )
        except Exception as e:
            print(f"Notification error: {e}")
        
        # Play audio alert
        self._play_alert()
        
        # Execute callback if provided
        if timer_id in self.callbacks:
            try:
                self.callbacks[timer_id]()
            except Exception as e:
                print(f"Callback error: {e}")
    
    def _play_alert(self):
        """Play audio alert for timer completion"""
        if not self.audio_enabled:
            print("🔊 BEEP BEEP! Timer completed!")
            return
            
        try:
            # Create a simple beep sound programmatically
            frequency = 800  # Hz
            duration = 0.5   # seconds
            sample_rate = 22050
            frames = int(duration * sample_rate)
            
            import numpy as np
            arr = np.zeros((frames, 2))
            arr[:, 0] = np.sin(2 * np.pi * frequency * np.linspace(0, duration, frames))
            arr[:, 1] = arr[:, 0]  # Stereo
            
            sound = pygame.sndarray.make_sound((arr * 32767).astype(np.int16))
            sound.play()
            
        except Exception as e:
            print(f"🔊 BEEP BEEP! Timer completed! (Audio error: {e})")

# Convenience functions for quick timer operations
def quick_timer(name: str, minutes: int) -> str:
    """Create and start a timer quickly"""
    manager = TimerManager()
    timer_id = manager.create_timer(name, minutes * 60)
    manager.start_timer(timer_id)
    return timer_id

def format_time(seconds: int) -> str:
    """Format seconds into MM:SS format"""
    minutes = seconds // 60
    seconds = seconds % 60
    return f"{minutes:02d}:{seconds:02d}"

# Test the timer functionality
if __name__ == "__main__":
    print("🍳 Super Spoon Timer Starting...")
    
    # Create a timer manager
    manager = TimerManager()
    
    # Create and start some test timers
    print("\n⏰ Creating test timers...")
    timer1 = manager.create_timer("Pasta Timer", 10)  # 10 seconds for testing
    timer2 = manager.create_timer("Sauce Timer", 15)  # 15 seconds for testing
    
    # Start the timers
    manager.start_timer(timer1)
    manager.start_timer(timer2)
    
    print("\n📊 Timer Status Updates:")
    
    # Monitor timers for 20 seconds
    for i in range(20):
        active_timers = manager.list_active_timers()
        
        if not active_timers:
            print("✅ All timers completed!")
            break
            
        for timer_id, status in active_timers.items():
            remaining = status['remaining']
            print(f"   {status['name']}: {format_time(remaining)} remaining")
        
        time.sleep(1)
        
    print("\n🎉 Timer test completed!")
