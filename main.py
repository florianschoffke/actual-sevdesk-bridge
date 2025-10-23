"""Main entry point for the SevDesk-Actual Budget sync application."""
import sys
import argparse
import logging
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

from src.config import get_config
from src.sync import sync_accounts, sync_categories, sync_vouchers
from src.storage import Database


def setup_logging(level: str = 'INFO'):
    """Setup logging configuration."""
    logging.basicConfig(
        level=getattr(logging, level.upper()),
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler('sync.log')
        ]
    )


def main():
    """Main application entry point."""
    parser = argparse.ArgumentParser(description='Sync data between SevDesk and Actual Budget')
    parser.add_argument('--log-level', default='INFO', help='Logging level')
    
    subparsers = parser.add_subparsers(dest='command', help='Available commands')
    
    # sync-accounts command
    accounts_parser = subparsers.add_parser('sync-accounts', help='Sync accounts from SevDesk to Actual Budget')
    accounts_parser.add_argument('--dry-run', action='store_true', help='Show what would be synced without making changes')
    
    # sync-categories command
    categories_parser = subparsers.add_parser('sync-categories', help='Sync cost centers to categories')
    categories_parser.add_argument('--dry-run', action='store_true', help='Show what would be synced without making changes')
    categories_parser.add_argument('--reconcile', action='store_true', help='Check for deleted categories and recreate them')
    
    # sync-vouchers command
    vouchers_parser = subparsers.add_parser('sync-vouchers', help='Sync vouchers to transactions')
    vouchers_parser.add_argument('--dry-run', action='store_true', help='Validate without making changes')
    vouchers_parser.add_argument('--limit', type=int, default=20, help='Maximum number of vouchers to process (default: 20)')
    vouchers_parser.add_argument('--full', action='store_true', help='Full sync (ignore last sync timestamp)')
    vouchers_parser.add_argument('--reconcile', action='store_true', help='Check for deleted/unbooked vouchers and remove transactions')
    
    # sync-all command  
    all_parser = subparsers.add_parser('sync-all', help='Sync categories and vouchers')
    all_parser.add_argument('--dry-run', action='store_true', help='Show what would be synced without making changes')
    all_parser.add_argument('--limit', type=int, help='Limit number of vouchers to sync (default: unlimited)')
    all_parser.add_argument('--voucher-limit', type=int, help='Alias for --limit (deprecated)')
    all_parser.add_argument('--reconcile', action='store_true', help='Enable reconciliation for both categories and transactions')
    
    # reset command
    reset_parser = subparsers.add_parser('reset', help='Reset transaction sync state')
    reset_parser.add_argument('--confirm', action='store_true', help='Confirm reset action')
    
    # history command
    subparsers.add_parser('history', help='Show recent sync history')
    
    # failed command
    failed_parser = subparsers.add_parser('failed', help='Show failed vouchers')
    failed_parser.add_argument('--clear', action='store_true', help='Clear failed vouchers to allow retry')
    failed_parser.add_argument('--confirm', action='store_true', help='Confirm clear action')
    
    # reconcile command
    reconcile_parser = subparsers.add_parser('reconcile', help='Find and remove transactions for unbooked/deleted vouchers')
    reconcile_parser.add_argument('--dry-run', action='store_true', help='Show what would be removed without making changes')
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return
    
    # Load configuration
    try:
        config = get_config()
        setup_logging(config.log_level)
        logger = logging.getLogger(__name__)
    except Exception as e:
        print(f"Error loading configuration: {e}")
        print("Make sure you have created a .env file with your credentials.")
        sys.exit(1)
    
    # Execute command
    try:
        if args.command == 'sync-accounts':
            result = sync_accounts(config, dry_run=args.dry_run)
            logger.info(f"📊 Result: {result}")
        
        elif args.command == 'sync-categories':
            result = sync_categories(config, dry_run=args.dry_run, reconcile=args.reconcile)
            logger.info(f"📊 Result: {result}")
        
        elif args.command == 'sync-vouchers':
            result = sync_vouchers(
                config,
                limit=args.limit,
                dry_run=args.dry_run,
                full_sync=args.full,
                reconcile=args.reconcile
            )
            logger.info(f"📊 Result: {result}")
        
        elif args.command == 'sync-all':
            # Use --limit, fallback to --voucher-limit for backwards compatibility
            limit = args.limit or args.voucher_limit
            reconcile = getattr(args, 'reconcile', False)
            
            logger.info("🚀 Starting complete synchronization...")
            if limit:
                logger.info(f"📊 Voucher limit: {limit}")
            if reconcile:
                logger.info("🔄 Reconciliation enabled")
            logger.info("")
            
            # Note: Account sync removed - using single account approach
            # User will manually manage accounts in Actual Budget UI
            
            # Stage 1: Categories
            result1 = sync_categories(config, dry_run=args.dry_run, reconcile=reconcile)
            logger.info(f"📊 Stage 1 Result: {result1}")
            logger.info("")
            
            # Stage 2: Vouchers (excludes Geldtransit and Durchlaufende Posten)
            result2 = sync_vouchers(
                config,
                limit=limit,
                dry_run=args.dry_run,
                reconcile=reconcile
            )
            logger.info(f"📊 Stage 2 Result: {result2}")
            logger.info("")
            logger.info("🎉 Complete synchronization finished!")
        
        elif args.command == 'reset':
            if not args.confirm:
                print("⚠️  Are you sure you want to reset transaction sync state?")
                print("This will clear all transaction mappings.")
                print("Run with --confirm to proceed.")
                return
            
            db = Database(config.db_path)
            deleted = db.clear_transaction_mappings()
            logger.info(f"✅ Reset complete: deleted {deleted} transaction mappings")
        
        elif args.command == 'history':
            db = Database(config.db_path)
            history = db.get_sync_history(limit=20)
            
            print("\n📜 Recent Sync History:")
            print("=" * 80)
            for entry in history:
                status_icon = "✅" if entry['status'] == 'completed' else "❌"
                print(f"\n{status_icon} {entry['sync_type'].upper()} - {entry['status']}")
                print(f"  Started:    {entry['started_at']}")
                if entry['completed_at']:
                    print(f"  Completed:  {entry['completed_at']}")
                print(f"  Processed:  {entry['items_processed']}")
                print(f"  Synced:     {entry['items_synced']}")
                if entry['items_failed']:
                    print(f"  Failed:     {entry['items_failed']}")
                if entry['error_message']:
                    print(f"  Error:      {entry['error_message'][:100]}")
            print()
        
        elif args.command == 'failed':
            db = Database(config.db_path)
            
            if args.clear:
                if not args.confirm:
                    print("⚠️  Are you sure you want to clear failed vouchers?")
                    print("This will allow them to be retried on next sync.")
                    print("Run with --confirm to proceed.")
                    return
                
                deleted = db.clear_failed_vouchers()
                logger.info(f"✅ Cleared {deleted} failed vouchers")
                return
            
            # Show failed vouchers
            failed = db.get_failed_vouchers(limit=100)
            
            if not failed:
                print("\n✅ No failed vouchers")
                return
            
            print(f"\n❌ Failed Vouchers ({len(failed)}):")
            print("=" * 120)
            print(f"{'ID':<12} {'Belegnummer':<15} {'Date':<12} {'Amount':>10} {'Type':<12} {'Retries':<8} {'Reason'}")
            print("-" * 120)
            
            for f in failed:
                date_str = f['voucher_date'][:10] if f['voucher_date'] else 'N/A'
                voucher_num = f.get('voucher_number', 'N/A') or 'N/A'
                print(
                    f"{f['sevdesk_voucher_id']:<12} {voucher_num:<15} {date_str:<12} "
                    f"€{f['amount']:>9.2f} {f['voucher_type']:<12} "
                    f"{f['retry_count']:<8} {f['failure_reason'][:40]}"
                )
            
            print("\n💡 To retry these vouchers after fixing in SevDesk:")
            print("   python3 main.py failed --clear --confirm")
            print()
        
        elif args.command == 'reconcile':
            # Import reconcile function
            from reconcile_vouchers import reconcile_vouchers
            
            result = reconcile_vouchers(dry_run=args.dry_run)
            
            if not args.dry_run:
                logger.info(f"📊 Reconciliation Result: {result}")
    
    except KeyboardInterrupt:
        logger.info("\n⚠️  Interrupted by user")
        sys.exit(1)
    except Exception as e:
        logger.error(f"❌ Error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == '__main__':
    main()
