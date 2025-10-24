"""Invoice synchronization between SevDesk and Actual Budget."""
import logging
from typing import TYPE_CHECKING, Dict

if TYPE_CHECKING:
    from src.config.settings import Config

from src.storage.database import Database
from src.api.sevdesk import SevDeskClient
from src.api.actual import ActualBudgetClient
from src.invoice_validator import InvoiceValidator
from src.notifications import EmailNotifier


def sync_invoices(config: 'Config', limit: int = None, dry_run: bool = False, reconcile: bool = False) -> dict:
    """
    Sync invoices from SevDesk to Actual Budget transactions.
    
    Only syncs invoices that have a cost center assigned. Invoices are synced as income
    transactions (negative amounts in Actual Budget).
    
    Args:
        config: Application configuration
        limit: Maximum number of invoices to sync (None = no limit)
        dry_run: If True, only validate and show what would be synced
        reconcile: If True, check for deleted invoices and remove their transactions
    
    Returns:
        Dict with sync statistics
    """
    logger = logging.getLogger(__name__)
    logger.info("=" * 60)
    logger.info("Invoice Synchronization")
    logger.info("=" * 60)
    
    db = Database(config.db_path)
    sevdesk = SevDeskClient(config.sevdesk_api_key)
    
    # Fetch paid invoices (status 1000)
    logger.info("📥 Fetching paid invoices from SevDesk...")
    invoices = sevdesk.get_invoices(status=1000, limit=limit)
    logger.info(f"Found {len(invoices)} paid invoices")
    
    if not invoices:
        logger.info("✅ No invoices to sync")
        return {
            'synced': 0,
            'skipped': 0,
            'failed': 0,
            'validated': 0,
            'deleted': 0
        }
    
    # Start sync tracking
    sync_id = db.start_sync('invoices')
    
    # Filter out Stornorechnung (cancellation invoices) and cancelled invoices
    filtered_invoices = []
    storno_count = 0
    cancelled_count = 0
    
    for inv in invoices:
        if 'Stornorechnung' in inv.get('header', ''):
            storno_count += 1
            continue
        
        # Check if invoice is cancelled - paid invoices with paidAmount = 0 are cancelled
        paid_amount = float(inv.get('paidAmount', 0))
        if paid_amount == 0:
            cancelled_count += 1
            continue
        
        filtered_invoices.append(inv)
    
    if storno_count > 0:
        logger.info(f"🚫 Filtered out {storno_count} Stornorechnung (cancellation invoices)")
    if cancelled_count > 0:
        logger.info(f"🚫 Filtered out {cancelled_count} cancelled invoices (paidAmount = 0)")
    
    # Use filtered invoices
    invoices = filtered_invoices
    
    # Get invoice IDs for batch position fetching
    invoice_ids = [str(inv.get('id')) for inv in invoices]
    
    # Fetch all positions in batch
    logger.info("📥 Fetching invoice positions in batch...")
    positions_by_invoice = sevdesk.get_invoice_positions_batch(invoice_ids, show_progress=True)
    
    # Get category mappings for validation
    category_mappings = {
        m['sevdesk_category_id']: m['actual_category_id']
        for m in db.get_all_category_mappings()
    }
    
    # Initialize validator
    validator = InvoiceValidator(category_mappings=category_mappings)
    
    # Fetch cost centers to enable manual invoice mappings
    logger.info("📥 Fetching cost centers for manual invoice mappings...")
    cost_centers = sevdesk.get_cost_centers()
    validator.set_cost_centers(cost_centers)
    
    # Validate all invoices
    logger.info("✅ Validating invoices...")
    valid_invoices = []
    already_synced = 0
    
    for invoice in invoices:
        invoice_id = str(invoice.get('id'))
        
        # Check if already synced
        existing_mapping = db.get_invoice_mapping(f"invoice_{invoice_id}")
        if existing_mapping and not existing_mapping.get('ignored'):
            already_synced += 1
            continue
        
        # Get positions
        positions = positions_by_invoice.get(invoice_id, [])
        
        # Validate
        result = validator.validate_invoice(invoice, positions)
        
        if result.is_valid:
            # Determine cost center
            invoice_number = result.invoice_number
            invoice_cost_centre = invoice.get('costCentre')
            cost_centre_id = None
            
            # First check for manual mapping
            if invoice_number in validator.MANUAL_INVOICE_COST_CENTERS:
                cost_center_name = validator.MANUAL_INVOICE_COST_CENTERS[invoice_number]
                cost_centre_id = validator.cost_center_name_to_id.get(cost_center_name)
            
            # If no manual mapping, get from invoice or positions
            if not cost_centre_id:
                if invoice_cost_centre and invoice_cost_centre.get('id'):
                    cost_centre_id = invoice_cost_centre.get('id')
                else:
                    # Get from first position
                    for pos in positions:
                        cc = pos.get('costCentre')
                        if cc and cc.get('id'):
                            cost_centre_id = cc.get('id')
                            break
            
            valid_invoices.append((invoice, cost_centre_id, result))
        else:
            logger.warning(f"Invoice {result.invoice_number} failed validation: {result.reason}")
    
    logger.info(f"✅ {len(valid_invoices)} invoices passed validation")
    logger.info(f"⏭️  {already_synced} invoices already synced")
    logger.info(f"❌ {len(validator.get_validation_errors())} invoices failed validation")
    
    # Send email notification if there are invalid invoices
    invalid_invoice_results = validator.get_validation_errors()
    if invalid_invoice_results and not dry_run:
        logger.info(f"📧 Sending email notification for {len(invalid_invoice_results)} invalid invoices...")
        try:
            # Convert validation results to dictionaries for email
            invalid_invoices = []
            for result in invalid_invoice_results:
                invalid_invoices.append({
                    'id': result.invoice_id,
                    'invoice_number': result.invoice_number,
                    'invoice_date': result.invoice_date,
                    'amount': result.amount,
                    'contact_name': '',  # Not available in validation result
                    'cost_center_id': '',
                    'cost_center_name': '',
                    'validation_reason': result.reason,
                    'last_validated_at': '',
                    'status': ''
                })
            
            email_notifier = EmailNotifier.from_config(config)
            email_notifier.send_validation_report(invalid_invoices, report_type='invoice')
            logger.info("✅ Email notification sent successfully")
        except Exception as e:
            logger.error(f"Failed to send email notification: {e}")
    
    if not valid_invoices:
        if dry_run:
            logger.info("✅ No new invoices to sync (DRY RUN)")
        else:
            logger.info("✅ No new invoices to sync")
        
        db.complete_sync(sync_id, status='completed', items_processed=len(invoices), items_synced=0)
        
        result = {
            'synced': 0,
            'skipped': already_synced,
            'failed': len(validator.get_validation_errors()),
            'validated': len(valid_invoices),
            'deleted': 0
        }
        
        if reconcile and not dry_run:
            from .reconciliation import reconcile_invoices
            with ActualBudgetClient(
                config.actual_url,
                config.actual_password,
                config.actual_file_id,
                config.actual_verify_ssl
            ) as actual:
                reconcile_result = reconcile_invoices(sevdesk, actual, db, config.actual_account_name, dry_run)
                result['deleted'] = reconcile_result['deleted']
        
        return result
    
    if dry_run:
        logger.info("=" * 60)
        logger.info("DRY RUN - Would sync the following invoices:")
        logger.info("")
        for invoice, cost_centre_id, result in valid_invoices[:10]:
            category_id = category_mappings.get(cost_centre_id, 'Unknown')
            logger.info(f"{result.invoice_date}   € {result.amount:8.2f} → Category: {category_id[:30]}")
        if len(valid_invoices) > 10:
            logger.info(f"... and {len(valid_invoices) - 10} more")
        logger.info("=" * 60)
        
        return {
            'synced': 0,
            'skipped': already_synced,
            'failed': len(validator.get_validation_errors()),
            'validated': len(valid_invoices),
            'deleted': 0
        }
    
    # Create transactions in Actual Budget
    logger.info(f"\nStep 4: Creating transactions in Actual Budget")
    logger.info("=" * 60)
    
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
        
        for invoice, cost_centre_id, result in valid_invoices:
            invoice_id = str(invoice.get('id'))
            invoice_number = result.invoice_number
            invoice_date_str = result.invoice_date
            amount = result.amount
            
            # Convert amount to cents (positive for income in Actual Budget)
            amount_cents = int(amount * 100)  # Positive = Inflow/Income
            
            # Parse date - handle ISO format with timezone
            from datetime import datetime
            # Invoice date comes as '2025-10-23T00:00:00+02:00', extract just the date part
            if 'T' in invoice_date_str:
                invoice_date_str = invoice_date_str.split('T')[0]
            invoice_date = datetime.strptime(invoice_date_str, '%Y-%m-%d').date()
            
            # Get category ID
            category_id = category_mappings.get(cost_centre_id)
            
            # Build notes
            notes = f"Invoice: {invoice_number}"
            contact = invoice.get('contact')
            if contact:
                contact_name = contact.get('name', '')
                if contact_name:
                    notes += f" | Customer: {contact_name}"
            
            try:
                # Create transaction
                transaction = actual.create_transaction(
                    account_id=account_id,
                    date=invoice_date,
                    amount=amount_cents,
                    category_id=category_id,
                    notes=notes
                )
                
                # Save mapping
                db.save_invoice_mapping(
                    sevdesk_id=f"invoice_{invoice_id}",
                    actual_id=transaction['id'],
                    invoice_date=invoice_date_str,
                    amount=amount,
                    update_timestamp=invoice.get('update')
                )
                
                created += 1
                logger.debug(f"✓ Created transaction for invoice {invoice_number}")
                
            except Exception as e:
                logger.error(f"Failed to create transaction for invoice {invoice_number}: {e}")
        
        logger.info(f"✓ Created {created} new transactions")
    
    # Mark sync as completed
    db.complete_sync(
        sync_id,
        status='completed',
        items_processed=len(invoices),
        items_synced=created
    )
    
    result = {
        'synced': created,
        'skipped': already_synced,
        'failed': len(validator.get_validation_errors()),
        'validated': len(valid_invoices),
        'deleted': 0
    }
    
    # Reconciliation phase
    if reconcile:
        logger.info("")
        logger.info("=" * 60)
        logger.info("Phase 2: Invoice Reconciliation")
        logger.info("=" * 60)
        
        from .reconciliation import reconcile_invoices
        
        with ActualBudgetClient(
            config.actual_url,
            config.actual_password,
            config.actual_file_id,
            config.actual_verify_ssl
        ) as actual:
            reconcile_result = reconcile_invoices(sevdesk, actual, db, config.actual_account_name, dry_run)
            result['deleted'] = reconcile_result['deleted']
    
    return result
