#!/usr/bin/env python3
"""
Reconciliation script to find and handle unbooked/deleted vouchers.

This script compares the local transaction mappings with the current state
in SevDesk to find vouchers that were unbooked or deleted, and removes
the corresponding transactions from Actual Budget.
"""
import sys
import logging
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from src.config import get_config
from src.storage.database import Database
from src.api.sevdesk import SevDeskClient
from src.api.actual import ActualBudgetClient

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def reconcile_vouchers(dry_run: bool = False) -> dict:
    """
    Reconcile transactions by finding unbooked/deleted vouchers.
    
    Process:
    1. Get all transaction mappings from local database
    2. For each mapped voucher, check current status in SevDesk
    3. If voucher is not booked (status != 1000) or doesn't exist:
       - Delete transaction in Actual Budget
       - Remove mapping from database
    
    Args:
        dry_run: If True, only report what would be done without making changes
    
    Returns:
        Dict with reconciliation statistics
    """
    logger.info("=" * 80)
    logger.info("VOUCHER RECONCILIATION")
    logger.info("=" * 80)
    
    if dry_run:
        logger.info("🔍 DRY RUN MODE - No changes will be made")
    
    config = get_config()
    db = Database(config.db_path)
    
    # Get all transaction mappings
    mappings = db.get_all_transaction_mappings()
    logger.info(f"Found {len(mappings)} transaction mappings to check")
    
    if not mappings:
        logger.info("✓ No mappings to reconcile")
        return {
            'checked': 0,
            'unbooked': 0,
            'deleted': 0,
            'not_found': 0,
            'errors': 0
        }
    
    unbooked_vouchers = []
    not_found_vouchers = []
    errors = []
    
    logger.info("")
    logger.info("Step 1: Checking voucher status in SevDesk")
    logger.info("=" * 80)
    
    with SevDeskClient(config.sevdesk_api_key) as sevdesk:
        for mapping in mappings:
            sevdesk_id = mapping['sevdesk_id']
            
            # Extract voucher ID (remove "voucher_" prefix if present)
            voucher_id = sevdesk_id.replace('voucher_', '')
            
            try:
                # Get voucher from SevDesk
                voucher = sevdesk.get_voucher(voucher_id)
                
                if not voucher:
                    # Voucher doesn't exist (deleted)
                    logger.warning(f"⚠️  Voucher {voucher_id} not found in SevDesk (deleted)")
                    not_found_vouchers.append(mapping)
                else:
                    # Check status
                    status = voucher.get('status')
                    if status != '1000':  # Not booked
                        logger.warning(f"⚠️  Voucher {voucher_id} status is {status} (not booked)")
                        unbooked_vouchers.append(mapping)
                    else:
                        # Still booked - OK
                        logger.debug(f"✓ Voucher {voucher_id} still booked")
                
            except Exception as e:
                logger.error(f"❌ Error checking voucher {voucher_id}: {str(e)}")
                errors.append({'voucher_id': voucher_id, 'error': str(e)})
    
    # Calculate totals
    to_remove = unbooked_vouchers + not_found_vouchers
    
    logger.info("")
    logger.info("Step 2: Reconciliation Summary")
    logger.info("=" * 80)
    logger.info(f"Total mappings checked: {len(mappings)}")
    logger.info(f"Still booked (OK): {len(mappings) - len(to_remove) - len(errors)}")
    logger.info(f"Unbooked vouchers: {len(unbooked_vouchers)}")
    logger.info(f"Deleted/not found: {len(not_found_vouchers)}")
    logger.info(f"Errors: {len(errors)}")
    logger.info(f"Total to remove: {len(to_remove)}")
    
    if not to_remove:
        logger.info("")
        logger.info("✅ All mapped transactions are still valid - no cleanup needed")
        return {
            'checked': len(mappings),
            'unbooked': 0,
            'deleted': 0,
            'not_found': 0,
            'errors': len(errors)
        }
    
    if dry_run:
        logger.info("")
        logger.info("Step 3: Would remove the following transactions (DRY RUN)")
        logger.info("=" * 80)
        
        for mapping in to_remove[:10]:  # Show first 10
            sevdesk_id = mapping['sevdesk_id'].replace('voucher_', '')
            actual_id = mapping['actual_id']
            amount = mapping.get('sevdesk_amount', 'Unknown')
            date = mapping.get('sevdesk_value_date', 'Unknown')
            
            logger.info(f"  Voucher {sevdesk_id}: €{amount} on {date}")
            logger.info(f"    → Would delete transaction {actual_id}")
        
        if len(to_remove) > 10:
            logger.info(f"  ... and {len(to_remove) - 10} more")
        
        logger.info("")
        logger.info("=" * 80)
        logger.info("DRY RUN COMPLETE - Run without --dry-run to apply changes")
        
        return {
            'checked': len(mappings),
            'unbooked': len(unbooked_vouchers),
            'deleted': len(not_found_vouchers),
            'not_found': len(not_found_vouchers),
            'errors': len(errors)
        }
    
    # Actually remove transactions and mappings
    logger.info("")
    logger.info("Step 3: Removing orphaned transactions")
    logger.info("=" * 80)
    
    deleted_count = 0
    mapping_removed_count = 0
    
    with ActualBudgetClient(
        config.actual_url,
        config.actual_password,
        config.actual_file_id,
        config.actual_verify_ssl
    ) as actual:
        for mapping in to_remove:
            sevdesk_id = mapping['sevdesk_id']
            voucher_id = sevdesk_id.replace('voucher_', '')
            actual_id = mapping['actual_id']
            
            try:
                # Delete transaction in Actual Budget
                if actual.delete_transaction(actual_id):
                    logger.info(f"✓ Deleted transaction {actual_id} (voucher {voucher_id})")
                    deleted_count += 1
                else:
                    logger.warning(f"⚠️  Transaction {actual_id} not found (already deleted?)")
                
                # Remove mapping from database
                if db.delete_transaction_mapping(sevdesk_id):
                    logger.debug(f"✓ Removed mapping for voucher {voucher_id}")
                    mapping_removed_count += 1
                else:
                    logger.warning(f"⚠️  Mapping for voucher {voucher_id} not found")
                    
            except Exception as e:
                logger.error(f"❌ Error removing voucher {voucher_id}: {str(e)}")
                errors.append({'voucher_id': voucher_id, 'error': str(e)})
    
    logger.info("")
    logger.info("=" * 80)
    logger.info("RECONCILIATION COMPLETE")
    logger.info("=" * 80)
    logger.info(f"✓ Deleted {deleted_count} transactions in Actual Budget")
    logger.info(f"✓ Removed {mapping_removed_count} mappings from database")
    
    if errors:
        logger.warning(f"⚠️  {len(errors)} errors occurred during reconciliation")
    
    return {
        'checked': len(mappings),
        'unbooked': len(unbooked_vouchers),
        'deleted': deleted_count,
        'not_found': len(not_found_vouchers),
        'mappings_removed': mapping_removed_count,
        'errors': len(errors)
    }


if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(
        description='Reconcile vouchers by finding and removing unbooked/deleted vouchers'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Show what would be done without making changes'
    )
    
    args = parser.parse_args()
    
    try:
        result = reconcile_vouchers(dry_run=args.dry_run)
        
        # Exit with appropriate code
        if result['errors'] > 0:
            sys.exit(1)
        else:
            sys.exit(0)
            
    except Exception as e:
        logger.error(f"❌ Reconciliation failed: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
