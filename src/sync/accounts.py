"""Account synchronization between SevDesk and Actual Budget."""
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.config.settings import Config

from src.storage.database import Database
from src.api.sevdesk import SevDeskClient
from src.api.actual import ActualBudgetClient


def sync_accounts(config: 'Config', dry_run: bool = False) -> dict:
    """
    Stage 1: Sync accounts from SevDesk to Actual Budget.
    
    This syncs CheckAccount objects from SevDesk to Actual Budget accounts.
    Accounts are matched by name (case-insensitive) and linked by ID in the database.
    
    Args:
        config: Application configuration
        dry_run: If True, only show what would be synced without making changes
    
    Returns:
        Dict with sync statistics: {'synced': int, 'created': int, 'skipped': int}
    """
    logger = logging.getLogger(__name__)
    logger.info("=" * 60)
    logger.info("STAGE 1: Account Synchronization")
    logger.info("=" * 60)
    
    db = Database(config.db_path)
    sevdesk = SevDeskClient(config.sevdesk_api_key)
    
    # Fetch accounts from SevDesk
    logger.info("Fetching accounts from SevDesk...")
    sevdesk_accounts = sevdesk.get_accounts()
    logger.info(f"Found {len(sevdesk_accounts)} SevDesk accounts")
    
    if dry_run:
        logger.info("DRY RUN - Would sync the following accounts:")
        for acc in sevdesk_accounts:
            acc_type = acc.get('type', 'unknown')
            status = acc.get('status', 0)
            status_str = "active" if status == 100 else "inactive"
            logger.info(f"  - {acc.get('name')} (ID: {acc.get('id')}, Type: {acc_type}, Status: {status_str})")
        return {'synced': 0, 'created': 0, 'skipped': 0}
    
    # Connect to Actual Budget
    with ActualBudgetClient(
        config.actual_url,
        config.actual_password,
        config.actual_file_id,
        config.actual_verify_ssl
    ) as actual:
        logger.info("Connected to Actual Budget")
        
        # Get existing accounts
        actual_accounts = actual.get_accounts()
        account_by_name = {a['name'].lower(): a for a in actual_accounts}
        
        sync_id = db.start_sync('accounts')
        synced = 0
        created = 0
        skipped = 0
        
        try:
            for sev_acc in sevdesk_accounts:
                acc_id = str(sev_acc.get('id'))
                acc_name = sev_acc.get('name', 'Unknown')
                acc_status = int(sev_acc.get('status', 0))
                
                # Skip inactive accounts
                if acc_status != 100:
                    logger.debug(f"Skipping inactive account: {acc_name}")
                    skipped += 1
                    continue
                
                # Check if already mapped (ID-based lookup)
                existing_mapping = db.get_account_mapping(acc_id)
                if existing_mapping:
                    logger.debug(f"Account '{acc_name}' already mapped (ID: {acc_id})")
                    synced += 1
                    continue
                
                # Find or create account in Actual Budget (name-based)
                actual_acc = account_by_name.get(acc_name.lower())
                
                if not actual_acc:
                    # Create new account
                    logger.info(f"Creating account: {acc_name}")
                    actual_acc = actual.create_account(acc_name, offbudget=False)
                    created += 1
                else:
                    logger.info(f"Found existing account: {acc_name}")
                
                # Save mapping (ID-based)
                db.save_account_mapping(
                    sevdesk_id=acc_id,
                    actual_id=actual_acc['id'],
                    sevdesk_name=acc_name,
                    actual_name=actual_acc['name']
                )
                synced += 1
                logger.info(f"✓ Mapped: {acc_name} (SevDesk {acc_id} → Actual {actual_acc['id']})")
            
            db.complete_sync(
                sync_id,
                status='completed',
                items_processed=len(sevdesk_accounts),
                items_synced=synced
            )
            
            logger.info("=" * 60)
            logger.info(f"✅ Stage 1 Complete: {synced} accounts mapped, {created} created, {skipped} skipped")
            logger.info("=" * 60)
            
            return {'synced': synced, 'created': created, 'skipped': skipped}
            
        except Exception as e:
            db.complete_sync(
                sync_id,
                status='failed',
                items_processed=len(sevdesk_accounts),
                items_synced=synced,
                error_message=str(e)
            )
            logger.error(f"Account sync failed: {e}")
            raise
