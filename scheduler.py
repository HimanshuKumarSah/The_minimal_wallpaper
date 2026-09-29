import datetime
import threading
import time


class DailyScheduler:
    def __init__(self, update_callback):
        self.update_callback = update_callback
        self.running = False
        self.thread = None
        self.last_updated_date = datetime.date.today().strftime("%Y-%m-%d")
        
    def start(self):
        if self.running:
            return
        self.running = True
        self.thread = threading.Thread(target=self._run_loop, daemon=True)
        self.thread.start()
        
    def stop(self):
        self.running = False
        
    def _run_loop(self):
        """
        Runs a check every 15 seconds. If date changed (e.g. at 12:00 midnight or after wake from sleep),
        triggers the callback.
        """
        while self.running:
            try:
                today_str = datetime.date.today().strftime("%Y-%m-%d")
                if today_str != self.last_updated_date:
                    print(f"[Scheduler] Date changed from {self.last_updated_date} to {today_str}. Updating wallpaper...")
                    self.last_updated_date = today_str
                    if self.update_callback:
                        self.update_callback(reason="midnight_daily_update")
            except Exception as e:
                print(f"[Scheduler] Error in scheduler loop: {e}")
                
            # Sleep in small slices so stopping is immediate
            for _ in range(15):
                if not self.running:
                    break
                time.sleep(1)

    @staticmethod
    def get_time_until_midnight():
        """Returns (hours, minutes, seconds) until next midnight."""
        now = datetime.datetime.now()
        tomorrow = (now + datetime.timedelta(days=1)).date()
        midnight = datetime.datetime.combine(tomorrow, datetime.time(0, 0, 0))
        delta = midnight - now
        total_seconds = max(0, int(delta.total_seconds()))
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        seconds = total_seconds % 60
        return hours, minutes, seconds
