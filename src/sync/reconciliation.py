"""Reconciliation module for detecting and fixing inconsistencies between SevDesk and Actual Budget."""
import logging
from typing import TYPE_CHECKING, Dict, List

if TYPE_CHECKING:
    from src.config.settings import Config
    from src.storage.database import Database
    from src.api.sevdesk import SevDeskClient
    from src.api.actual import ActualBudgetClient


def reconcile_transactions(
    sevdesk: 'SevDeskClient',
    actual: 'ActualBudgetClient',
    db: 'Database',
    dry_run: bool = False
) -> Dict:
    """
    Reconcile transactions by finding unbooked/deleted vouchers.
    
    Process:
    1. Get all transaction mappings from local database
    2. For each mapped voucher, check current status in SevDesk
    3. If voucher is not booked (status != 1000) or doesn't exist:
       - Delete transaction in Actual Budget
       - Remove mapping from database
    
    Args:
        sevdesk: SevDesk API client
        actual: Actual Budget API client
        db: Database instance
        dry_run: If True, only report what would be done without making changes
    
    Returns:
        Dict with reconciliation statistics
    """
    logger = logging.getLogger(__name__)
    logger.info("=" * 60)
    logger.info("TRANSACTION RECONCILIATION")
    logger.info("=" * 60)
    
    if dry_run:
        logger.info("🔍 DRY RUN MODE - No changes will be made")
    
    # Get all transaction mappings
    mappings = db.get_all_transaction_mappings()
    logger.info(f"Checking {len(mappings)} transaction mappings...")
    
    if not mappings:
        logger.info("✓ No mappings to reconcile")
        return {
            'checked': 0,
            'deleted': 0,
            'errors': 0
        }
    
    unbooked_vouchers = []
    not_found_vouchers = []
    errors = []
    
    # Check each voucher's current status
    for idx, mapping in enumerate(mappings, 1):
        sevdesk_id = mapping['sevdesk_id']
        voucher_id = sevdesk_id.replace('voucher_', '')
        
        try:
            # Get voucher from SevDesk
            voucher = sevdesk.get_voucher(voucher_id)
            
            if not voucher:
                # Voucher doesn't exist (deleted)
                logger.debug(f"Voucher {voucher_id} not found in SevDesk (deleted)")
                not_found_vouchers.append(mapping)
            else:
                # Check status
                status = voucher.get('status')
                if status != '1000':  # Not booked
                    logger.debug(f"Voucher {voucher_id} status is {status} (not booked)")
                    unbooked_vouchers.append(mapping)
                # else: Still booked - OK
            
            # Log progress every 10%
            if idx % max(1, len(mappings) // 10) == 0:
                percent = int((idx / len(mappings)) * 100)
                logger.info(f"Progress: {percent}% ({idx}/{len(mappings)})")
                
        except Exception as e:
            logger.error(f"Error checking voucher {voucher_id}: {str(e)}")
            errors.append({'voucher_id': voucher_id, 'error': str(e)})
    
    # Calculate totals
    to_remove = unbooked_vouchers + not_found_vouchers
    
    logger.info(f"Results: {len(mappings) - len(to_remove) - len(errors)} OK, "
                f"{len(unbooked_vouchers)} unbooked, "
                f"{len(not_found_vouchers)} deleted, "
                f"{len(errors)} errors")
    
    if not to_remove:
        logger.info("✅ All transactions are valid - no cleanup needed")
        return {
            'checked': len(mappings),
            'deleted': 0,
            'errors': len(errors)
        }
    
    if dry_run:
        logger.info(f"Would remove {len(to_remove)} transactions (DRY RUN)")
        for mapping in to_remove[:5]:  # Show first 5
            voucher_id = mapping['sevdesk_id'].replace('voucher_', '')
            logger.info(f"  - Voucher {voucher_id}: transaction {mapping['actual_id']}")
        if len(to_remove) > 5:
            logger.info(f"  ... and {len(to_remove) - 5} more")
        
        return {
            'checked': len(mappings),
            'deleted': 0,
            'errors': len(errors)
        }
    
    # Actually remove transactions and mappings
    logger.info(f"Removing {len(to_remove)} orphaned transactions...")
    deleted_count = 0
    
    for mapping in to_remove:
        sevdesk_id = mapping['sevdesk_id']
        voucher_id = sevdesk_id.replace('voucher_', '')
        actual_id = mapping['actual_id']
        
        try:
            # Delete transaction in Actual Budget
            if actual.delete_transaction(actual_id):
                deleted_count += 1
            
            # Remove mapping from database
            db.delete_transaction_mapping(sevdesk_id)
                
        except Exception as e:
            logger.error(f"Error removing voucher {voucher_id}: {str(e)}")
            errors.append({'voucher_id': voucher_id, 'error': str(e)})
    
    logger.info(f"✅ Deleted {deleted_count} transactions, removed {len(to_remove)} mappings")
    
    return {
        'checked': len(mappings),
        'deleted': deleted_count,
        'errors': len(errors)
    }


def reconcile_categories(
    sevdesk: 'SevDeskClient',
    actual: 'ActualBudgetClient',
    db: 'Database',
    config: 'Config',
    dry_run: bool = False
) -> Dict:
    """
    Reconcile categories by detecting deleted categories and recreating them.
    
    Process:
    1. Get all category mappings from database
    2. Get all categories from Actual Budget
    3. For each mapping, check if category still exists in Actual Budget
    4. If category was deleted, recreate it
    
    Args:
        sevdesk: SevDesk API client
        actual: Actual Budget API client
        db: Database instance
        config: Application configuration
        dry_run: If True, only report what would be done without making changes
    
    Returns:
        Dict with reconciliation statistics
    """
    logger = logging.getLogger(__name__)
    logger.info("=" * 60)
    logger.info("CATEGORY RECONCILIATION")
    logger.info("=" * 60)
    
    if dry_run:
        logger.info("🔍 DRY RUN MODE - No changes will be made")
    
    # Get SevDesk cost centers (source of truth)
    cost_centers = sevdesk.get_cost_centers()
    sevdesk_categories = {str(cc['id']): cc for cc in cost_centers}
    logger.info(f"Found {len(sevdesk_categories)} cost centers in SevDesk")
    
    # Get current mappings from database
    db_mappings = db.get_all_category_mappings()
    logger.info(f"Found {len(db_mappings)} category mappings in database")
    
    # Get actual categories from Actual Budget
    actual_categories = actual.get_categories()
    actual_category_ids = {c['id'] for c in actual_categories}
    logger.info(f"Found {len(actual_categories)} categories in Actual Budget")
    
    deleted_categories = []
    errors = []
    
    # Check each mapping
    for mapping in db_mappings:
        sevdesk_id = mapping['sevdesk_category_id']
        actual_id = mapping['actual_category_id']
        
        # Check if category still exists in Actual Budget
        if actual_id not in actual_category_ids:
            # Category was deleted in Actual Budget
            sevdesk_cat = sevdesk_categories.get(sevdesk_id)
            if sevdesk_cat:
                logger.warning(f"Category '{mapping['sevdesk_category_name']}' was deleted in Actual Budget")
                deleted_categories.append({
                    'mapping': mapping,
                    'sevdesk_cat': sevdesk_cat
                })
            else:
                logger.debug(f"Category mapping {sevdesk_id} no longer in SevDesk - skipping")
    
    if not deleted_categories:
        logger.info("✅ All categories are present - no recreation needed")
        return {
            'checked': len(db_mappings),
            'recreated': 0,
            'errors': len(errors)
        }
    
    logger.info(f"Found {len(deleted_categories)} deleted categories to recreate")
    
    if dry_run:
        for item in deleted_categories:
            logger.info(f"  Would recreate: {item['sevdesk_cat']['name']}")
        return {
            'checked': len(db_mappings),
            'recreated': 0,
            'errors': len(errors)
        }
    
    # Recreate deleted categories
    recreated_count = 0
    default_group = actual.get_or_create_category_group("SevDesk Categories")
    income_group = actual.get_or_create_category_group("Income")
    
    for item in deleted_categories:
        mapping = item['mapping']
        sevdesk_cat = item['sevdesk_cat']
        cat_name = sevdesk_cat['name']
        
        try:
            # Determine if income category
            is_income = cat_name in config.income_categories
            target_group = income_group if is_income else default_group
            
            # Recreate category
            logger.info(f"Recreating category: {cat_name}")
            new_category = actual.create_category(cat_name, target_group, is_income=is_income)
            
            # Update mapping with new ID
            db.update_category_mapping(mapping['sevdesk_category_id'], new_category['id'])
            recreated_count += 1
            
        except Exception as e:
            logger.error(f"Error recreating category {cat_name}: {str(e)}")
            errors.append({'category': cat_name, 'error': str(e)})
    
    logger.info(f"✅ Recreated {recreated_count} categories")
    
    return {
        'checked': len(db_mappings),
        'recreated': recreated_count,
        'errors': len(errors)
    }


def reconcile_accounts(
    sevdesk: 'SevDeskClient',
    actual: 'ActualBudgetClient',
    db: 'Database',
    dry_run: bool = False
) -> Dict:
    """
    Reconcile accounts by detecting deleted accounts and recreating them.
    
    Process:
    1. Get all account mappings from database
    2. Get all accounts from Actual Budget
    3. For each mapping, check if account still exists in Actual Budget
    4. If account was deleted, recreate it
    
    Args:
        sevdesk: SevDesk API client
        actual: Actual Budget API client
        db: Database instance
        dry_run: If True, only report what would be done without making changes
    
    Returns:
        Dict with reconciliation statistics
    """
    logger = logging.getLogger(__name__)
    logger.info("=" * 60)
    logger.info("ACCOUNT RECONCILIATION")
    logger.info("=" * 60)
    
    if dry_run:
        logger.info("🔍 DRY RUN MODE - No changes will be made")
    
    # Get SevDesk accounts (source of truth)
    sevdesk_accounts_list = sevdesk.get_accounts()
    sevdesk_accounts = {
        str(acc['id']): acc 
        for acc in sevdesk_accounts_list 
        if acc.get('status') == 100  # Only active accounts
    }
    logger.info(f"Found {len(sevdesk_accounts)} active accounts in SevDesk")
    
    # Get current mappings from database
    db_mappings = db.get_all_account_mappings()
    logger.info(f"Found {len(db_mappings)} account mappings in database")
    
    # Get actual accounts from Actual Budget
    actual_accounts = actual.get_accounts()
    actual_account_ids = {a['id'] for a in actual_accounts if not a.get('closed')}
    logger.info(f"Found {len(actual_account_ids)} open accounts in Actual Budget")
    
    deleted_accounts = []
    errors = []
    
    # Check each mapping
    for mapping in db_mappings:
        sevdesk_id = mapping['sevdesk_account_id']
        actual_id = mapping['actual_account_id']
        
        # Check if account still exists in Actual Budget
        if actual_id not in actual_account_ids:
            # Account was deleted in Actual Budget
            sevdesk_acc = sevdesk_accounts.get(sevdesk_id)
            if sevdesk_acc:
                logger.warning(f"Account '{mapping['sevdesk_account_name']}' was deleted in Actual Budget")
                deleted_accounts.append({
                    'mapping': mapping,
                    'sevdesk_acc': sevdesk_acc
                })
            else:
                logger.debug(f"Account mapping {sevdesk_id} no longer active in SevDesk - skipping")
    
    if not deleted_accounts:
        logger.info("✅ All accounts are present - no recreation needed")
        return {
            'checked': len(db_mappings),
            'recreated': 0,
            'errors': len(errors)
        }
    
    logger.info(f"Found {len(deleted_accounts)} deleted accounts to recreate")
    
    if dry_run:
        for item in deleted_accounts:
            logger.info(f"  Would recreate: {item['sevdesk_acc']['name']}")
        return {
            'checked': len(db_mappings),
            'recreated': 0,
            'errors': len(errors)
        }
    
    # Recreate deleted accounts
    recreated_count = 0
    
    for item in deleted_accounts:
        mapping = item['mapping']
        sevdesk_acc = item['sevdesk_acc']
        acc_name = sevdesk_acc['name']
        
        try:
            # Recreate account
            logger.info(f"Recreating account: {acc_name}")
            new_account = actual.create_account(acc_name, offbudget=False)
            
            # Update mapping with new ID
            db.update_account_mapping(mapping['sevdesk_account_id'], new_account['id'])
            recreated_count += 1
            
        except Exception as e:
            logger.error(f"Error recreating account {acc_name}: {str(e)}")
            errors.append({'account': acc_name, 'error': str(e)})
    
    logger.info(f"✅ Recreated {recreated_count} accounts")
    
    return {
        'checked': len(db_mappings),
        'recreated': recreated_count,
        'errors': len(errors)
    }


def reconcile_invoices(
    sevdesk: 'SevDeskClient',
    actual: 'ActualBudgetClient',
    db: 'Database',
    dry_run: bool = False
) -> Dict:
    """
    Reconcile invoice transactions by finding deleted invoices.
    
    Process:
    1. Get all invoice mappings from local database
    2. For each mapped invoice, check if it still exists in SevDesk
    3. If invoice doesn't exist or is not paid:
       - Delete transaction in Actual Budget
       - Remove mapping from database
    
    Args:
        sevdesk: SevDesk API client
        actual: Actual Budget API client
        db: Database instance
        dry_run: If True, only report what would be done without making changes
    
    Returns:
        Dict with reconciliation statistics
    """
    logger = logging.getLogger(__name__)
    logger.info("=" * 60)
    logger.info("INVOICE RECONCILIATION")
    logger.info("=" * 60)
    
    if dry_run:
        logger.info("🔍 DRY RUN MODE - No changes will be made")
    
    # Get all invoice mappings
    mappings = db.get_all_invoice_mappings()
    logger.info(f"Checking {len(mappings)} invoice mappings...")
    
    if not mappings:
        logger.info("✓ No mappings to reconcile")
        return {
            'checked': 0,
            'deleted': 0,
            'errors': 0
        }
    
    not_found_invoices = []
    not_paid_invoices = []
    errors = []
    
    # Check each invoice's current status
    for idx, mapping in enumerate(mappings, 1):
        sevdesk_id = mapping['sevdesk_id']
        invoice_id = sevdesk_id.replace('invoice_', '')
        
        try:
            # Get invoice from SevDesk
            invoice = sevdesk.get_invoice(invoice_id)
            
            if not invoice:
                # Invoice doesn't exist (deleted)
                logger.debug(f"Invoice {invoice_id} not found in SevDesk (deleted)")
                not_found_invoices.append(mapping)
            else:
                # Check status
                status = invoice.get('status')
                if status != '1000':  # Not paid
                    logger.debug(f"Invoice {invoice_id} status is {status} (not paid)")
                    not_paid_invoices.append(mapping)
                # else: Still paid - OK
            
            # Log progress every 10%
            if idx % max(1, len(mappings) // 10) == 0:
                percent = int((idx / len(mappings)) * 100)
                logger.info(f"Progress: {percent}% ({idx}/{len(mappings)})")
                
        except Exception as e:
            logger.error(f"Error checking invoice {invoice_id}: {str(e)}")
            errors.append({'invoice_id': invoice_id, 'error': str(e)})
    
    # Calculate totals
    to_remove = not_found_invoices + not_paid_invoices
    
    logger.info(f"Results: {len(mappings) - len(to_remove) - len(errors)} OK, "
                f"{len(not_paid_invoices)} not paid, "
                f"{len(not_found_invoices)} deleted, "
                f"{len(errors)} errors")
    
    if not to_remove:
        logger.info("✅ All invoices are valid - no cleanup needed")
        return {
            'checked': len(mappings),
            'deleted': 0,
            'errors': len(errors)
        }
    
    if dry_run:
        logger.info(f"Would remove {len(to_remove)} transactions (DRY RUN)")
        for mapping in to_remove[:5]:  # Show first 5
            invoice_id = mapping['sevdesk_id'].replace('invoice_', '')
            logger.info(f"  - Invoice {invoice_id}: transaction {mapping['actual_id']}")
        if len(to_remove) > 5:
            logger.info(f"  ... and {len(to_remove) - 5} more")
        
        return {
            'checked': len(mappings),
            'deleted': 0,
            'errors': len(errors)
        }
    
    # Actually remove transactions and mappings
    logger.info(f"Removing {len(to_remove)} orphaned transactions...")
    deleted_count = 0
    
    for mapping in to_remove:
        sevdesk_id = mapping['sevdesk_id']
        invoice_id = sevdesk_id.replace('invoice_', '')
        actual_id = mapping['actual_id']
        
        try:
            # Delete transaction in Actual Budget
            if actual.delete_transaction(actual_id):
                deleted_count += 1
            
            # Remove mapping from database
            db.delete_invoice_mapping(sevdesk_id)
                
        except Exception as e:
            logger.error(f"Error removing invoice {invoice_id}: {str(e)}")
            errors.append({'invoice_id': invoice_id, 'error': str(e)})
    
    logger.info(f"✅ Deleted {deleted_count} transactions, removed {len(to_remove)} mappings")
    
    return {
        'checked': len(mappings),
        'deleted': deleted_count,
        'errors': len(errors)
    }
