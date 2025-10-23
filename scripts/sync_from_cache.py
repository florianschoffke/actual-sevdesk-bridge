#!/usr/bin/env python3
"""
Sync all vouchers from local cache to Actual Budget without fetching from SevDesk.
Use this after deleting transactions in Actual Budget to re-sync everything from cache.
"""
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

from src.config import get_config
from src.storage import Database
from src.api.actual import ActualBudgetClient
from src.voucher_validator import VoucherValidator
from src.sync.categories import sync_categories
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def main():
    config = get_config()
    db = Database(config.db_path)
    
    logger.info("=" * 60)
    logger.info("Sync from Cache to Actual Budget")
    logger.info("=" * 60)
    
    # Step 1: Sync categories first
    logger.info("\n📂 Step 1: Syncing categories...")
    logger.info("-" * 60)
    category_result = sync_categories(config)
    logger.info(f"✅ Categories: {category_result.get('synced', 0)} synced, {category_result.get('created', 0)} created\n")
    
    logger.info("💰 Step 2: Syncing vouchers...")
    logger.info("-" * 60)
    
    # Get all cached vouchers
    logger.info("📦 Loading vouchers from cache...")
    vouchers = db.get_cached_vouchers()
    logger.info(f"   Found {len(vouchers)} cached vouchers")
    
    if not vouchers:
        logger.error("❌ No cached vouchers found. Run a normal sync first.")
        return 1
    
    # Get voucher IDs
    voucher_ids = [str(v.get('id')) for v in vouchers]
    
    # Load positions from cache
    logger.info("📥 Loading positions from cache...")
    positions_by_voucher = db.get_cached_positions_batch(voucher_ids)
    logger.info(f"   Loaded positions for {len(positions_by_voucher)} vouchers")
    
    # Get mappings
    logger.info("📋 Loading account and category mappings...")
    account_mappings = {
        m['sevdesk_account_id']: m['actual_account_id']
        for m in db.get_all_account_mappings()
    }
    category_mappings = {
        m['sevdesk_category_id']: m['actual_category_id']
        for m in db.get_all_category_mappings()
    }
    
    logger.info(f"   {len(account_mappings)} account mappings")
    logger.info(f"   {len(category_mappings)} category mappings")
    
    if not account_mappings:
        logger.error("❌ No account mappings found. Run 'python3 main.py sync-accounts' first.")
        return 1
    
    # Initialize validator
    validator = VoucherValidator(account_mappings, category_mappings)
    
    # Validate vouchers
    logger.info("✅ Validating vouchers...")
    valid_vouchers = []
    ignored_count = 0
    
    for voucher in vouchers:
        voucher_id = str(voucher.get('id'))
        positions = positions_by_voucher.get(voucher_id, [])
        
        # Check if this voucher should be ignored (Geldtransit or Durchlaufende Posten)
        if positions:
            accounting_type_ids = [p.get('accountingType', {}).get('id') for p in positions]
            # Skip Geldtransit (40, 81) and Durchlaufende Posten (39)
            if any(t in ['39', '40', '81'] for t in accounting_type_ids):
                # Check if not already marked as ignored
                if not db.is_voucher_ignored(f"voucher_{voucher_id}"):
                    # Determine reason
                    if '39' in accounting_type_ids:
                        reason = "Durchlaufende Posten"
                    else:
                        reason = "Geldtransit"
                    
                    db.mark_voucher_ignored(f"voucher_{voucher_id}", reason)
                
                ignored_count += 1
                continue
        
        result = validator.validate_voucher(voucher, positions)
        
        # Mark validation in DB
        db.mark_voucher_validation(voucher_id, result.is_valid, result.reason)
        
        if result.is_valid:
            valid_vouchers.append(voucher)
    
    logger.info(f"   {len(valid_vouchers)} valid vouchers")
    logger.info(f"   {ignored_count} vouchers ignored (Geldtransit/Durchlaufende Posten)")
    logger.info(f"   {len(vouchers) - len(valid_vouchers) - ignored_count} invalid vouchers")
    
    if not valid_vouchers:
        logger.info("✅ No valid vouchers to sync")
        return 0
    
    # Connect to Actual Budget
    logger.info("🔗 Connecting to Actual Budget...")
    with ActualBudgetClient(
        config.actual_url,
        config.actual_password,
        config.actual_file_id,
        config.actual_verify_ssl
    ) as actual:
        logger.info("   Connected!")
        
        # Get or create the default account
        account = actual.get_or_create_account(config.actual_account_name, offbudget=False)
        account_id = account['id']
        logger.info(f"   Using account: {account['name']} ({account_id})")
        
        # Sync valid vouchers
        logger.info(f"💰 Syncing {len(valid_vouchers)} vouchers to Actual Budget...")
        
        # Prepare transactions for bulk import
        transactions_to_import = []
        voucher_lookup = {}
        
        from datetime import datetime
        
        for voucher in valid_vouchers:
            voucher_id = str(voucher['id'])
            
            # Check if already synced
            existing_mapping = db.get_transaction_mapping(voucher_id)
            if existing_mapping:
                continue
            
            # Parse voucher data
            voucher_date_str = voucher['voucherDate']
            voucher_date = datetime.fromisoformat(voucher_date_str).date()
            
            # Convert amount to cents
            amount_eur = float(voucher['sumGross'])
            credit_debit = voucher.get('creditDebit', 'D')
            amount_cents = int(amount_eur * 100)
            if credit_debit == 'C':
                amount_cents = -amount_cents
            
            # Get category ID
            cc = voucher.get('costCentre', {})
            cc_id = str(cc.get('id', ''))
            category_id = category_mappings.get(cc_id) if cc_id else None
            
            # Use voucher ID as imported_id for deduplication
            imported_id = f"sevdesk_voucher_{voucher_id}"
            
            # Create notes with voucher info for better tracking
            voucher_number = voucher.get('voucherNumber', '')
            notes_parts = []
            if voucher_number:
                notes_parts.append(f"Voucher: {voucher_number}")
            notes_parts.append(f"ID: {voucher_id}")
            notes = " | ".join(notes_parts)
            
            # Create unique imported_payee by appending voucher ID to prevent deduplication
            base_payee = voucher.get('supplier', {}).get('name', '') or voucher.get('description', '') or ''
            if base_payee:
                imported_payee = f"{base_payee} [#{voucher_id}]"
            else:
                imported_payee = f"Voucher #{voucher_id}"
            
            # Prepare transaction
            transactions_to_import.append({
                'date': voucher_date,
                'amount': amount_cents,
                'category_id': category_id,
                'imported_id': imported_id,
                'imported_payee': imported_payee,
                'notes': notes,
                'cleared': False
            })
            
            voucher_lookup[imported_id] = voucher
        
        if not transactions_to_import:
            logger.info("   All vouchers already synced!")
        else:
            logger.info(f"   Importing {len(transactions_to_import)} transactions...")
            
            result = actual.import_transactions(account_id, transactions_to_import)
            
            added_count = len(result.get('added', []))
            updated_count = len(result.get('updated', []))
            skipped_count = len(result.get('skipped', []))
            
            logger.info(f"   Added: {added_count}")
            logger.info(f"   Updated: {updated_count}")
            logger.info(f"   Skipped: {skipped_count}")
            
            # Save mappings for all imported transactions
            # Note: We'll save mappings for all since we used imported_id for deduplication
            for voucher_id_str, voucher in voucher_lookup.items():
                voucher_id = str(voucher['id'])
                
                # The transaction should exist now (either added or updated)
                db.save_transaction_mapping(
                    sevdesk_id=voucher_id,
                    actual_id=f"unknown_{voucher_id}",  # We don't have the actual ID, but that's ok
                    sevdesk_value_date=voucher.get('voucherDate'),
                    sevdesk_amount=float(voucher.get('sumNet', 0)),
                    sevdesk_update_timestamp=voucher.get('update')
                )
    
    logger.info("=" * 60)
    logger.info("✅ Sync Complete!")
    logger.info(f"   Total: {len(transactions_to_import)}")
    logger.info("=" * 60)
    
    return 0

if __name__ == '__main__':
    sys.exit(main())
