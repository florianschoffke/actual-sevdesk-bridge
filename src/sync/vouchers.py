"""Voucher synchronization between SevDesk and Actual Budget."""
import logging
import warnings
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, List, Dict

# Suppress SSL warnings for cleaner output
warnings.filterwarnings('ignore', message='Unverified HTTPS request')

if TYPE_CHECKING:
    from src.config.settings import Config

from src.storage.database import Database
from src.api.sevdesk import SevDeskClient
from src.api.actual import ActualBudgetClient
from src.voucher_validator import VoucherValidator
from src.notifications import EmailNotifier


def sync_vouchers(config: 'Config', limit: int = None, dry_run: bool = False, full_sync: bool = False) -> dict:
    """
    Stage 3: Sync vouchers from SevDesk to Actual Budget transactions.
    
    Only syncs BOOKED vouchers (status 1000). Supports incremental syncing by
    tracking the last sync timestamp and only fetching vouchers modified since then.
    
    Args:
        config: Application configuration
        limit: Maximum number of vouchers to sync (None = no limit)
        dry_run: If True, only validate and show what would be synced
        full_sync: If True, ignore last sync and fetch all vouchers
    
    Returns:
        Dict with sync statistics: {'synced': int, 'skipped': int, 'failed': int, 'validated': int}
    """
    logger = logging.getLogger(__name__)
    logger.info("=" * 60)
    logger.info("Voucher Synchronization")
    logger.info("=" * 60)
    
    db = Database(config.db_path)
    sevdesk = SevDeskClient(config.sevdesk_api_key)
    
    # Check if we have cached vouchers
    cache_stats = db.get_voucher_cache_stats()
    has_cache = cache_stats['voucher_count'] > 0
    
    if has_cache and not full_sync:
        # Incremental sync using cache
        logger.info("📦 Using voucher cache for incremental sync")
        logger.info(f"   Cached vouchers: {cache_stats['voucher_count']}")
        logger.info(f"   Last cache update: {cache_stats['last_update']}")
        
        # Get max update timestamp from cache
        max_update_timestamp = db.get_max_update_timestamp()
        
        # Fetch vouchers updated since last sync
        logger.info(f"📥 Fetching vouchers updated since {max_update_timestamp}...")
        updated_vouchers = sevdesk.get_vouchers(status=1000, limit=limit)
        
        # Filter to only those actually updated
        if max_update_timestamp:
            updated_vouchers = [
                v for v in updated_vouchers
                if v.get('update', '') > max_update_timestamp
            ]
        
        logger.info(f"   Found {len(updated_vouchers)} updated vouchers")
        
        # Also fetch previously invalid vouchers to re-validate
        invalid_ids = db.get_invalid_voucher_ids()
        logger.info(f"   Found {len(invalid_ids)} previously invalid vouchers to re-check")
        
        # Fetch invalid vouchers individually
        invalid_vouchers = []
        if invalid_ids:
            logger.info("🔄 Re-fetching previously invalid vouchers...")
            total_invalid = len(invalid_ids)
            last_logged = -10
            
            for idx, voucher_id in enumerate(invalid_ids, 1):
                try:
                    voucher = sevdesk.get_voucher(voucher_id)
                    if voucher:
                        invalid_vouchers.append(voucher)
                except Exception as e:
                    logger.warning(f"Failed to fetch voucher {voucher_id}: {e}")
                
                # Log progress every 10%
                percent = int((idx / total_invalid) * 100)
                if percent >= last_logged + 10:
                    logger.info(f"🔄 Fetching invalid vouchers: {percent}% ({idx}/{total_invalid})")
                    last_logged = percent
            
            if total_invalid > 0:
                logger.info(f"🔄 Fetching invalid vouchers: 100% ({total_invalid}/{total_invalid})")
        
        # Combine updated and invalid vouchers
        vouchers = updated_vouchers + invalid_vouchers
        logger.info(f"� Total vouchers to process: {len(vouchers)}")
        
    else:
        # First sync or full sync - fetch all vouchers
        if full_sync:
            logger.info("📅 Full sync: Fetching all booked vouchers")
        else:
            logger.info("📅 First sync: Fetching all booked vouchers and building cache")
        
        vouchers = sevdesk.get_vouchers(status=1000, limit=limit)
        logger.info(f"Found {len(vouchers)} booked vouchers to process")
    
    if not vouchers:
        logger.info("✅ No vouchers to sync")
        return {'synced': 0, 'skipped': 0, 'ignored': 0, 'failed': 0, 'validated': 0}
    
    # Start sync tracking
    sync_id = db.start_sync('vouchers')
    
    # Save/update vouchers in cache
    logger.info("💾 Updating voucher cache...")
    db.save_vouchers_to_cache_batch(vouchers)
    
    # Get voucher IDs for batch position fetching
    voucher_ids = [str(v.get('id')) for v in vouchers]
    
    # Fetch all positions in batch (much faster!)
    logger.info("📥 Fetching voucher positions in batch...")
    positions_by_voucher = sevdesk.get_voucher_positions_batch(voucher_ids, show_progress=True)
    
    # Save positions to cache
    logger.info("💾 Updating position cache...")
    db.save_positions_to_cache_batch(positions_by_voucher)
    
    # Get mappings for validation
    account_mappings = {
        m['sevdesk_account_id']: m['actual_account_id']
        for m in db.get_all_account_mappings()
    }
    category_mappings = {
        m['sevdesk_category_id']: m['actual_category_id']
        for m in db.get_all_category_mappings()
    }
    
    # Initialize validator
    validator = VoucherValidator(
        account_mappings=account_mappings,
        category_mappings=category_mappings
    )
    
    # Validate all vouchers (now fast - no API calls!)
    logger.info("✅ Validating vouchers...")
    
    valid_vouchers = []
    modified_vouchers = []
    already_synced = 0
    ignored_count = 0
    
    total = len(vouchers)
    last_logged_percent = -10
    
    for idx, voucher in enumerate(vouchers, 1):
        voucher_id = str(voucher.get('id'))
        
        # Check if already synced successfully
        existing_mapping = db.get_transaction_mapping(f"voucher_{voucher_id}")
        if existing_mapping:
            # Check if voucher was modified since last sync
            current_update = voucher.get('update')
            stored_update = existing_mapping.get('sevdesk_update_timestamp')
            
            if current_update and stored_update and current_update > stored_update:
                # Voucher was modified - need to update
                logger.debug(f"Voucher {voucher_id} was modified (stored: {stored_update}, current: {current_update})")
                # Continue to validation and mark as modified
            else:
                # No change - skip
                already_synced += 1
                
                # Log progress
                percent = int((idx / total) * 100)
                if percent >= last_logged_percent + 10:
                    logger.info(f"✅ Validating: {percent}% ({idx}/{total})")
                    last_logged_percent = percent
                continue
        
        # Get positions from cache (no API call!)
        positions = positions_by_voucher.get(voucher_id, [])
        
        # Check if this voucher should be ignored (Geldtransit or Durchlaufende Posten WITHOUT cost centre)
        if positions:
            accounting_type_ids = [p.get('accountingType', {}).get('id') for p in positions]
            
            # Check for Geldtransit (40, 81) - always ignore these
            if any(t in ['40', '81'] for t in accounting_type_ids):
                if not db.is_voucher_ignored(f"voucher_{voucher_id}"):
                    if not dry_run:
                        db.mark_voucher_ignored(f"voucher_{voucher_id}", "Geldtransit")
                ignored_count += 1
                
                # Log progress
                percent = int((idx / total) * 100)
                if percent >= last_logged_percent + 10:
                    logger.info(f"✅ Validating: {percent}% ({idx}/{total})")
                    last_logged_percent = percent
                continue
            
            # Check for Durchlaufende Posten (39) - must have cost centre
            if '39' in accounting_type_ids:
                # Check if voucher has a cost centre
                cost_centre = voucher.get('costCentre')
                has_cost_centre = cost_centre and cost_centre.get('id')
                
                if not has_cost_centre:
                    # No cost centre - mark as erroneous
                    voucher_number = voucher.get('voucherNumber') or voucher.get('description', '')
                    failure_reason = "Durchlaufende Posten requires a cost centre"
                    
                    if not dry_run:
                        # Mark validation status
                        db.mark_voucher_validation(
                            voucher_id=voucher_id,
                            is_valid=False,
                            reason=failure_reason
                        )
                        
                        # Save as failed voucher
                        db.save_failed_voucher(
                            voucher_id=voucher_id,
                            voucher_date=voucher.get('voucherDate'),
                            amount=float(voucher.get('sumNet', 0)),
                            voucher_type=voucher.get('voucherType'),
                            failure_reason=failure_reason,
                            voucher_number=voucher_number
                        )
                    
                    # Log progress
                    percent = int((idx / total) * 100)
                    if percent >= last_logged_percent + 10:
                        logger.info(f"✅ Validating: {percent}% ({idx}/{total})")
                        last_logged_percent = percent
                    continue
                # else: Has cost centre - proceed with validation
        
        # Get voucher number for better identification
        voucher_number = voucher.get('voucherNumber') or voucher.get('description', '')
        
        # Validate
        result = validator.validate_voucher(voucher, positions, voucher_number)
        
        # Mark validation status in cache
        if not dry_run:
            db.mark_voucher_validation(
                voucher_id=voucher_id,
                is_valid=result.is_valid,
                reason=result.reason if not result.is_valid else None
            )
        
        if result.is_valid:
            if existing_mapping:
                # Mark as modified (for update)
                modified_vouchers.append((voucher, positions, result, existing_mapping))
            else:
                # New voucher (for creation)
                valid_vouchers.append((voucher, positions, result))
        else:
            # Save/update failed voucher in database
            if not dry_run:
                db.save_failed_voucher(
                    voucher_id=result.voucher_id,
                    voucher_date=result.voucher_date,
                    amount=result.amount,
                    voucher_type=result.voucher_type,
                    failure_reason=result.reason,
                    voucher_number=voucher_number
                )
        
        # Log progress
        percent = int((idx / total) * 100)
        if percent >= last_logged_percent + 10:
            logger.info(f"✅ Validating: {percent}% ({idx}/{total})")
            last_logged_percent = percent
    
    if total > 0:
        logger.info(f"✅ Validating: 100% ({total}/{total})")
    
    logger.info(f"✅ {len(valid_vouchers)} new vouchers passed validation")
    logger.info(f"🔄 {len(modified_vouchers)} modified vouchers will be updated")
    logger.info(f"⏭️  {already_synced} vouchers already synced (unchanged)")
    logger.info(f"🚫 {ignored_count} vouchers ignored (Geldtransit/Durchlaufende Posten)")
    logger.info(f"❌ {len(validator.get_validation_errors())} vouchers failed validation")
    
    if already_synced > 0:
        logger.info(f"   ⚡ Skipped {already_synced} unchanged vouchers (incremental sync)")
    
    logger.info("")
    
    # Print validation errors
    validator.print_validation_summary(logger)
    
    # Export validation errors to file
    output_file = "invalid_vouchers.md"
    validator.export_validation_errors_to_file(output_file)
    if validator.get_validation_errors():
        logger.info(f"📄 Invalid vouchers exported to: {output_file}")
    
    if dry_run:
        logger.info("=" * 60)
        logger.info("DRY RUN - Would sync the following valid vouchers:")
        logger.info("")
        logger.info(f"{'Date':<12} {'Amount':>10} {'Type':<12} {'Category/Transfer'}")
        logger.info("-" * 70)
        
        for voucher, positions, result in valid_vouchers[:20]:
            date_str = result.voucher_date[:10] if result.voucher_date else 'N/A'
            amount = result.amount
            voucher_type = result.voucher_type
            
            if voucher_type == 'geldtransit':
                detail = "Transfer between accounts"
            else:
                cc = voucher.get('costCentre', {})
                cc_id = str(cc.get('id', ''))
                category_name = category_mappings.get(cc_id, 'Unknown')[:30]
                detail = f"Category: {category_name}"
            
            logger.info(f"{date_str:<12} €{amount:>9.2f} {voucher_type:<12} {detail}")
        
        if len(valid_vouchers) > 20:
            logger.info(f"  ... and {len(valid_vouchers) - 20} more")
        
        logger.info("=" * 60)
        
        # Mark dry run as completed (but with status 'dry_run')
        db.complete_sync(
            sync_id,
            status='dry_run',
            items_processed=len(vouchers),
            items_synced=0
        )
        
        return {
            'synced': 0,
            'skipped': already_synced,
            'ignored': ignored_count,
            'failed': len(validator.get_validation_errors()),
            'validated': len(valid_vouchers)
        }
    
    # Step 4: Create/update transactions in Actual Budget
    total_to_process = len(valid_vouchers) + len(modified_vouchers)
    if total_to_process == 0:
        logger.info("✓ No vouchers to sync")
        
        # Send email notification if there are invalid vouchers
        invalid_vouchers = db.get_invalid_vouchers()
        if invalid_vouchers:
            logger.info(f"📧 Sending email notification for {len(invalid_vouchers)} invalid vouchers...")
            try:
                email_notifier = EmailNotifier.from_config(config)
                email_notifier.send_validation_report(invalid_vouchers)
            except Exception as e:
                logger.error(f"Failed to send email notification: {e}")
        
        return {
            'synced': 0,
            'skipped': already_synced,
            'ignored': ignored_count,
            'failed': len(validator.get_validation_errors()),
            'validated': 0
        }
    
    logger.info(f"\nStep 4: Creating/updating transactions in Actual Budget")
    logger.info("=" * 60)
    
    # Get or create the single configured account
    with ActualBudgetClient(
        config.actual_url,
        config.actual_password,
        config.actual_file_id,
        config.actual_verify_ssl
    ) as actual:
        account = actual.get_or_create_account(config.actual_account_name, offbudget=False)
        account_id = account['id']
        logger.info(f"Using account: {account['name']} ({account_id})")
        
        created = 0
        updated = 0
        
        # Process new vouchers (import transactions using importTransactions-like behavior)
        if valid_vouchers:
            logger.info(f"Importing {len(valid_vouchers)} new transactions...")
            
            # Prepare all transaction data for import
            transactions_to_import = []
            voucher_lookup = {}  # Map imported_id -> voucher metadata
            
            for voucher, positions, result in valid_vouchers:
                # Parse voucher data
                voucher_id = str(voucher['id'])
                voucher_date_str = voucher['voucherDate']
                voucher_date = datetime.fromisoformat(voucher_date_str).date()
                
                # Convert amount to cents
                amount_eur = float(voucher['sumGross'])
                credit_debit = voucher.get('creditDebit', 'D')
                amount_cents = int(amount_eur * 100)
                if credit_debit == 'C':
                    amount_cents = -amount_cents
                
                # Get category ID from mapping
                cc = voucher.get('costCentre', {})
                cc_id = str(cc.get('id', ''))
                category_id = category_mappings.get(cc_id) if cc_id else None
                
                # Use voucher ID as imported_id for deduplication
                imported_id = f"sevdesk_voucher_{voucher_id}"
                
                # Create notes with voucher info for better tracking
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
                
                # Prepare transaction data for import
                transactions_to_import.append({
                    'date': voucher_date,
                    'amount': amount_cents,
                    'category_id': category_id,
                    'imported_id': imported_id,
                    'imported_payee': imported_payee,
                    'notes': notes,
                    'cleared': False
                })
                
                # Store metadata for later mapping
                voucher_lookup[imported_id] = {
                    'voucher_id': voucher_id,
                    'voucher_date_str': voucher_date_str,
                    'amount_eur': amount_eur,
                    'update_timestamp': voucher.get('update')
                }
            
            # Import transactions one-by-one to avoid bulk deduplication issues
            logger.info(f"Importing {len(transactions_to_import)} new/updated transactions...")
            
            result = actual.import_transactions(account_id, transactions_to_import)
            
            # Save mappings for newly added AND updated transactions
            for txn_id in result['added'] + result['updated']:
                # Find the voucher metadata - need to query which imported_id this transaction has
                from actual.database import Transactions
                from sqlalchemy import select
                
                stmt = select(Transactions).where(Transactions.id == txn_id)
                txn = actual._actual.session.execute(stmt).scalar_one()
                
                if txn.financial_id and txn.financial_id in voucher_lookup:
                    metadata = voucher_lookup[txn.financial_id]
                    db.save_transaction_mapping(
                        sevdesk_id=f"voucher_{metadata['voucher_id']}",
                        actual_id=txn_id,
                        sevdesk_value_date=metadata['voucher_date_str'],
                        sevdesk_amount=metadata['amount_eur'],
                        sevdesk_update_timestamp=metadata['update_timestamp']
                    )
            
            created = len(result['added']) + len(result['updated'])  # Count both as "created" for stats
            logger.info(f"✓ Imported {len(result['added'])} new transactions, {len(result['updated'])} updated, {len(result['skipped'])} skipped as duplicates")
        
        # Process modified vouchers (update transactions in batch)
        if modified_vouchers:
            logger.info(f"Updating {len(modified_vouchers)} modified transactions in batch...")
            
            # Prepare all update data
            transactions_to_update = []
            voucher_metadata = []
            
            for voucher, positions, result, existing_mapping in modified_vouchers:
                # Parse voucher data
                voucher_id = str(voucher['id'])
                voucher_date_str = voucher['voucherDate']
                voucher_date = datetime.fromisoformat(voucher_date_str).date()
                
                # Convert amount to cents
                amount_eur = float(voucher['sumGross'])
                credit_debit = voucher.get('creditDebit', 'D')
                amount_cents = int(amount_eur * 100)
                if credit_debit == 'C':
                    amount_cents = -amount_cents
                
                # Get category ID from mapping
                cc = voucher.get('costCentre', {})
                cc_id = str(cc.get('id', ''))
                category_id = category_mappings.get(cc_id) if cc_id else None
                
                # Add to batch
                transactions_to_update.append({
                    'id': existing_mapping['actual_id'],
                    'date': voucher_date,
                    'amount': amount_cents,
                    'category_id': category_id
                })
                
                # Store metadata for later mapping update
                voucher_metadata.append({
                    'voucher_id': voucher_id,
                    'actual_id': existing_mapping['actual_id'],
                    'voucher_date_str': voucher_date_str,
                    'amount_eur': amount_eur,
                    'update_timestamp': voucher.get('update')
                })
            
            try:
                # Batch update all transactions at once
                actual.update_transactions_batch(transactions_to_update)
                
                # Update all mappings in database
                for metadata in voucher_metadata:
                    db.save_transaction_mapping(
                        sevdesk_id=f"voucher_{metadata['voucher_id']}",
                        actual_id=metadata['actual_id'],
                        sevdesk_value_date=metadata['voucher_date_str'],
                        sevdesk_amount=metadata['amount_eur'],
                        sevdesk_update_timestamp=metadata['update_timestamp']
                    )
                
                updated = len(transactions_to_update)
                logger.info(f"✓ Updated {updated} transactions in batch")
                
            except Exception as e:
                logger.error(f"Batch update failed: {str(e)}")
                logger.warning("Falling back to individual transaction updates...")
                
                # Fallback: Update one by one
                total_updates = len(modified_vouchers)
                last_logged = -10
                
                for idx, (voucher, positions, result, existing_mapping) in enumerate(modified_vouchers, 1):
                    try:
                        voucher_id = str(voucher['id'])
                        voucher_date_str = voucher['voucherDate']
                        voucher_date = datetime.fromisoformat(voucher_date_str).date()
                        
                        amount_eur = float(voucher['sumGross'])
                        credit_debit = voucher.get('creditDebit', 'D')
                        amount_cents = int(amount_eur * 100)
                        if credit_debit == 'C':
                            amount_cents = -amount_cents
                        
                        cc = voucher.get('costCentre', {})
                        cc_id = str(cc.get('id', ''))
                        category_id = category_mappings.get(cc_id) if cc_id else None
                        
                        actual.update_transaction(
                            transaction_id=existing_mapping['actual_id'],
                            date=voucher_date,
                            amount=amount_cents,
                            category_id=category_id
                        )
                        
                        db.save_transaction_mapping(
                            sevdesk_id=f"voucher_{voucher_id}",
                            actual_id=existing_mapping['actual_id'],
                            sevdesk_value_date=voucher_date_str,
                            sevdesk_amount=amount_eur,
                            sevdesk_update_timestamp=voucher.get('update')
                        )
                        
                        updated += 1
                        
                        # Log progress every 10%
                        percent = int((idx / total_updates) * 100)
                        if percent >= last_logged + 10:
                            logger.info(f"🔄 Updating: {percent}% ({idx}/{total_updates})")
                            last_logged = percent
                        
                    except Exception as e2:
                        logger.error(f"Failed to update transaction for voucher {voucher_id}: {str(e2)}")
                
                if total_updates > 0:
                    logger.info(f"🔄 Updating: 100% ({total_updates}/{total_updates})")
        
        logger.info(f"✓ Created {created} new transactions")
        logger.info(f"✓ Updated {updated} modified transactions")
    
    # Mark sync as completed
    db.complete_sync(
        sync_id,
        status='completed',
        items_processed=len(vouchers),
        items_synced=created + updated
    )
    
    # Send email notification if there are invalid vouchers
    invalid_vouchers = db.get_invalid_vouchers()
    if invalid_vouchers:
        logger.info(f"📧 Sending email notification for {len(invalid_vouchers)} invalid vouchers...")
        try:
            email_notifier = EmailNotifier.from_config(config)
            email_notifier.send_validation_report(invalid_vouchers)
        except Exception as e:
            logger.error(f"Failed to send email notification: {e}")
    
    return {
        'synced': created + updated,
        'created': created,
        'updated': updated,
        'skipped': already_synced,
        'ignored': ignored_count,
        'failed': len(validator.get_validation_errors()) + (len(valid_vouchers) - created) + (len(modified_vouchers) - updated),
        'validated': len(valid_vouchers) + len(modified_vouchers),
        'invalid': len(invalid_vouchers)
    }
