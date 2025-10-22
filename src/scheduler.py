"""Cron scheduler for sync operations."""
import time
import logging
from datetime import datetime, timedelta
from typing import Callable


class CronScheduler:
    """Simple cron scheduler implementation."""
    
    def __init__(self, cron_expression: str):
        """
        Initialize scheduler with cron expression.
        
        Args:
            cron_expression: Cron format string "minute hour day month day_of_week"
                           minute: 0-59
                           hour: 0-23  
                           day: 1-31
                           month: 1-12
                           day_of_week: 0-6 (Sunday=0)
                           Use * for "any"
        
        Examples:
            "0 18 * * 2"  = Every Tuesday at 6 PM
            "0 * * * *"   = Every hour
            "30 14 * * 1" = Every Monday at 2:30 PM
        """
        self.cron_expression = cron_expression
        self.logger = logging.getLogger(__name__)
        
        # Parse cron expression
        try:
            parts = cron_expression.split()
            if len(parts) != 5:
                raise ValueError("Cron expression must have 5 parts")
            
            self.minute, self.hour, self.day, self.month, self.day_of_week = parts
            self.logger.info(f"📅 Scheduled: {self._describe_schedule()}")
        except Exception as e:
            raise ValueError(f"Invalid cron expression '{cron_expression}': {e}")
    
    def _describe_schedule(self) -> str:
        """Generate human-readable description of the schedule."""
        # Day of week names
        days = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]
        
        desc_parts = []
        
        # Time
        if self.minute == "0" and self.hour != "*":
            if self.hour == "*":
                desc_parts.append("every hour")
            else:
                hour_num = int(self.hour)
                time_str = f"{hour_num}:00" if hour_num < 10 else f"{hour_num}:00"
                desc_parts.append(f"at {time_str}")
        elif self.minute != "*" and self.hour != "*":
            hour_num = int(self.hour)
            minute_num = int(self.minute)
            time_str = f"{hour_num:02d}:{minute_num:02d}"
            desc_parts.append(f"at {time_str}")
        
        # Day of week
        if self.day_of_week != "*":
            day_num = int(self.day_of_week)
            desc_parts.append(f"every {days[day_num]}")
        elif self.day != "*":
            desc_parts.append(f"on day {self.day} of the month")
        elif len(desc_parts) == 1:  # Just time specified
            desc_parts.append("every day")
        
        return " ".join(desc_parts)
    
    def _matches_time(self, dt: datetime) -> bool:
        """Check if current datetime matches cron schedule."""
        # Check minute
        if self.minute != "*" and dt.minute != int(self.minute):
            return False
        
        # Check hour  
        if self.hour != "*" and dt.hour != int(self.hour):
            return False
        
        # Check day of month
        if self.day != "*" and dt.day != int(self.day):
            return False
        
        # Check month
        if self.month != "*" and dt.month != int(self.month):
            return False
        
        # Check day of week (0=Sunday, 1=Monday, etc.)
        if self.day_of_week != "*":
            # Python weekday(): Monday=0, Sunday=6
            # Cron weekday: Sunday=0, Monday=1, ..., Saturday=6  
            cron_weekday = (dt.weekday() + 1) % 7
            if cron_weekday != int(self.day_of_week):
                return False
        
        return True
    
    def get_next_run_time(self) -> datetime:
        """Calculate the next time the schedule should run."""
        now = datetime.now().replace(second=0, microsecond=0)
        
        # Start from next minute
        next_time = now + timedelta(minutes=1)
        
        # Check up to 1 year ahead (reasonable limit)
        for _ in range(365 * 24 * 60):  # 1 year in minutes
            if self._matches_time(next_time):
                return next_time
            next_time += timedelta(minutes=1)
        
        raise RuntimeError("Could not find next run time within 1 year")
    
    def wait_until_next_run(self) -> None:
        """Sleep until the next scheduled run time."""
        next_run = self.get_next_run_time()
        now = datetime.now()
        
        if next_run <= now:
            self.logger.info("🚀 Schedule time reached, running now...")
            return
        
        wait_seconds = (next_run - now).total_seconds()
        self.logger.info(f"⏰ Next run: {next_run.strftime('%Y-%m-%d %H:%M:%S')}")
        self.logger.info(f"💤 Waiting {wait_seconds:.0f} seconds...")
        
        time.sleep(wait_seconds)
        self.logger.info("🚀 Schedule time reached, running now...")
    
    def run_scheduled(self, func: Callable) -> None:
        """
        Run a function on the cron schedule.
        
        Args:
            func: Function to run on schedule
        """
        self.logger.info(f"🕐 Starting scheduler: {self._describe_schedule()}")
        
        while True:
            try:
                self.wait_until_next_run()
                
                # Run the scheduled function
                self.logger.info("▶️  Executing scheduled task...")
                func()
                self.logger.info("✅ Scheduled task completed")
                
            except KeyboardInterrupt:
                self.logger.info("⏹️  Scheduler stopped by user")
                break
            except Exception as e:
                self.logger.error(f"❌ Error in scheduled task: {e}")
                # Continue running despite errors