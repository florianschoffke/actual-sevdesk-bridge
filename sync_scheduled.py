"""Scheduled sync runner using cron expressions."""
import sys
import logging
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

from src.config import get_config
from src.sync import sync_categories, sync_vouchers
from src.scheduler import CronScheduler


def setup_logging(level: str = 'INFO'):
    """Setup logging configuration."""
    logging.basicConfig(
        level=getattr(logging, level.upper()),
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[logging.StreamHandler()]
    )


def run_sync():
    """Run a complete sync cycle."""
    logger = logging.getLogger(__name__)
    
    try:
        config = get_config()
        
        logger.info("🔄 Starting sync cycle...")
        logger.info("")
        
        # Stage 1: Categories
        result1 = sync_categories(config, dry_run=False)
        logger.info(f"📊 Categories Result: {result1}")
        logger.info("")
        
        # Stage 2: Vouchers (no limit - full sync)
        result2 = sync_vouchers(config, limit=None, dry_run=False)
        logger.info(f"📊 Vouchers Result: {result2}")
        logger.info("")
        
        logger.info("🎉 Sync cycle completed successfully!")
        
    except Exception as e:
        logger.error(f"❌ Sync cycle failed: {e}")
        raise


def main():
    """Main entry point for scheduled sync."""
    try:
        # Load configuration
        config = get_config()
        setup_logging(config.log_level)
        logger = logging.getLogger(__name__)
        
        logger.info("🚀 Starting Actual-SevDesk Bridge (Scheduled)")
        logger.info(f"📋 Schedule: {config.sync_schedule}")
        logger.info("")
        
        # Run initial sync on startup
        logger.info("🔄 Running startup sync...")
        run_sync()
        logger.info("")
        
        # Create and start scheduler for future runs
        scheduler = CronScheduler(config.sync_schedule)
        scheduler.run_scheduled(run_sync)
        
    except KeyboardInterrupt:
        print("\n⏹️  Stopped by user")
    except Exception as e:
        print(f"❌ Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()