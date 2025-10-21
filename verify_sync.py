#!/usr/bin/env python3
"""Verify sync consistency between SevDesk and Actual Budget."""
import sys
from pathlib import Path
from decimal import Decimal
from io import StringIO

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / 'src'))

from config.settings import get_config
from storage.database import Database
from api.actual import ActualBudgetClient
from notifications.email_notifier import EmailNotifier
from actual.database import Transactions
from sqlalchemy import select, and_, func
import logging

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(message)s'
)
logger = logging.getLogger(__name__)


def verify_sync_consistency(send_email_always=False):
    """
    Verify that SevDesk data matches Actual Budget data.
    
    Args:
        send_email_always: If True, send email even if all checks pass
    """
    
    config = get_config()
    
    # Capture all output to send in email
    output_buffer = StringIO()
    
    def log(msg):
        """Log to both console and buffer."""
        print(msg)
        output_buffer.write(msg + "\n")
    
    # Use sqlite3 directly
    import sqlite3
    conn = sqlite3.connect(config.db_path)
    
    log("\n" + "="*80)
    log("🔍 SYNC CONSISTENCY CHECK")
    log("="*80 + "\n")
    
    # ========================================================================
    # 1. Check voucher counts
    # ========================================================================
    log("📊 Step 1: Voucher Counts")
    log("-" * 80)
    
    # Count valid vouchers in cache (not ignored)
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT COUNT(*) 
        FROM voucher_cache 
        WHERE status != 'draft'
    """)
    total_cached_vouchers = cursor.fetchone()[0]
    
    # Count mapped transactions (not ignored)
    cursor.execute("""
        SELECT COUNT(*) 
        FROM transaction_mappings
        WHERE ignored = 0
    """)
    valid_vouchers = cursor.fetchone()[0]
    
    # Count ignored transactions
    cursor.execute("""
        SELECT COUNT(*) 
        FROM transaction_mappings
        WHERE ignored = 1
    """)
    ignored_vouchers = cursor.fetchone()[0]
    
    log(f"   Total cached vouchers:       {total_cached_vouchers:,}")
    log(f"   Valid vouchers (to sync):    {valid_vouchers:,}")
    log(f"   Ignored vouchers (39/40/81): {ignored_vouchers:,}")
    
    # Count transaction mappings
    cursor.execute("SELECT COUNT(*) FROM transaction_mappings")
    mapped_transactions = cursor.fetchone()[0]
    
    log(f"   Mapped transactions in DB:   {mapped_transactions:,}")
    
    # ========================================================================
    # 2. Check Actual Budget transaction count
    # ========================================================================
    log(f"\n📊 Step 2: Actual Budget Transactions")
    log("-" * 80)
    
    with ActualBudgetClient(
        base_url=config.actual_url,
        password=config.actual_password,
        file_id=config.actual_file_id,
        verify_ssl=config.actual_verify_ssl
    ) as actual:
        
        # Get the EGB Funds account
        accounts = actual.get_accounts()
        egb_account = next((acc for acc in accounts if acc['name'] == 'EGB Funds'), None)
        
        if not egb_account:
            log("   ❌ ERROR: EGB Funds account not found in Actual Budget!")
            return False
        
        account_id = egb_account['id']
        
        # Count transactions with imported_id (from SevDesk)
        stmt = select(func.count(Transactions.id)).where(
            and_(
                Transactions.acct == account_id,
                Transactions.financial_id.isnot(None),
                Transactions.financial_id.like('sevdesk_voucher_%'),
                Transactions.tombstone == 0
            )
        )
        imported_txn_count = actual._actual.session.execute(stmt).scalar()
        
        # Count all transactions (including manual)
        stmt = select(func.count(Transactions.id)).where(
            and_(
                Transactions.acct == account_id,
                Transactions.tombstone == 0
            )
        )
        total_txn_count = actual._actual.session.execute(stmt).scalar()
        
        log(f"   Imported transactions:       {imported_txn_count:,} (with sevdesk_voucher_* ID)")
        log(f"   Total transactions:          {total_txn_count:,} (including manual)")
        
        # ====================================================================
        # 3. Compare counts
        # ====================================================================
        log(f"\n✅ Step 3: Consistency Check")
        log("-" * 80)
        
        all_checks_pass = True
        
        # Check 1: Valid vouchers should equal imported transactions
        if valid_vouchers == imported_txn_count:
            log(f"   ✅ Valid vouchers ({valid_vouchers:,}) = Imported transactions ({imported_txn_count:,})")
        else:
            log(f"   ❌ MISMATCH: Valid vouchers ({valid_vouchers:,}) ≠ Imported transactions ({imported_txn_count:,})")
            log(f"      Difference: {abs(valid_vouchers - imported_txn_count):,} transactions")
            all_checks_pass = False
        
        # Check 2: Total mapped (valid + ignored) should equal total in mappings table
        total_expected_mappings = valid_vouchers + ignored_vouchers
        if mapped_transactions == total_expected_mappings:
            log(f"   ✅ Total mapped ({mapped_transactions:,}) = Valid ({valid_vouchers:,}) + Ignored ({ignored_vouchers:,})")
        else:
            log(f"   ❌ MISMATCH: Mapped transactions ({mapped_transactions:,}) ≠ Expected ({total_expected_mappings:,})")
            log(f"      Difference: {abs(mapped_transactions - total_expected_mappings):,} transactions")
            all_checks_pass = False
        
        # ====================================================================
        # 4. Check for amount mismatches
        # ====================================================================
        log(f"\n📊 Step 4: Amount Verification")
        log("-" * 80)
        
        # Get sample of transactions and verify amounts match
        cursor.execute("""
            SELECT 
                vc.id as voucher_id,
                vc.amount,
                tm.actual_id
            FROM voucher_cache vc
            JOIN transaction_mappings tm ON tm.sevdesk_id = vc.id
            WHERE vc.status != 'draft'
            AND tm.ignored = 0
            LIMIT 100
        """)
        
        sample_vouchers = cursor.fetchall()
        amount_mismatches = []
        
        for voucher_id, voucher_amount, actual_txn_id in sample_vouchers:
            # Get transaction from Actual Budget
            stmt = select(Transactions).where(
                and_(
                    Transactions.id == actual_txn_id,
                    Transactions.tombstone == 0
                )
            )
            txn = actual._actual.session.execute(stmt).scalar_one_or_none()
            
            if txn:
                # Compare amounts (Actual uses cents, SevDesk amount is already stored as decimal)
                expected_amount = int(Decimal(str(voucher_amount)) * 100)
                if txn.amount != expected_amount:
                    amount_mismatches.append({
                        'voucher_id': voucher_id,
                        'expected': expected_amount,
                        'actual': txn.amount,
                        'difference': txn.amount - expected_amount
                    })
        
        if not amount_mismatches:
            log(f"   ✅ Sample check: All {len(sample_vouchers)} voucher amounts match")
        else:
            log(f"   ❌ MISMATCH: {len(amount_mismatches)} out of {len(sample_vouchers)} vouchers have amount differences")
            for mismatch in amount_mismatches[:5]:  # Show first 5
                log(f"      Voucher {mismatch['voucher_id']}: Expected {mismatch['expected']/100:.2f}€, Got {mismatch['actual']/100:.2f}€")
            all_checks_pass = False
        
        # ====================================================================
        # 5. Check for duplicate imported_ids
        # ====================================================================
        log(f"\n📊 Step 5: Duplicate Detection")
        log("-" * 80)
        
        # Check for duplicate imported_ids in Actual Budget
        stmt = select(
            Transactions.financial_id,
            func.count(Transactions.id).label('count')
        ).where(
            and_(
                Transactions.acct == account_id,
                Transactions.financial_id.isnot(None),
                Transactions.financial_id.like('sevdesk_voucher_%'),
                Transactions.tombstone == 0
            )
        ).group_by(Transactions.financial_id).having(func.count(Transactions.id) > 1)
        
        duplicates = actual._actual.session.execute(stmt).all()
        
        if not duplicates:
            log(f"   ✅ No duplicate imported_ids found")
        else:
            log(f"   ❌ WARNING: {len(duplicates)} duplicate imported_ids found:")
            for imported_id, count in duplicates[:5]:  # Show first 5
                log(f"      {imported_id}: {count} transactions")
            all_checks_pass = False
        
        # ====================================================================
        # 6. Check for orphaned mappings
        # ====================================================================
        log(f"\n📊 Step 6: Orphaned Mappings")
        log("-" * 80)
        
        # Check for mappings where transaction no longer exists
        cursor.execute("""
            SELECT COUNT(*)
            FROM transaction_mappings tm
            WHERE NOT EXISTS (
                SELECT 1 
                FROM voucher_cache vc 
                WHERE vc.id = tm.sevdesk_id
            )
        """)
        orphaned_mappings = cursor.fetchone()[0]
        
        if orphaned_mappings == 0:
            log(f"   ✅ No orphaned mappings (all mappings have corresponding vouchers)")
        else:
            log(f"   ⚠️  WARNING: {orphaned_mappings} mappings without corresponding vouchers")
            log(f"      (This can happen if vouchers are deleted from cache)")
            # Don't fail on this - it's just a warning
        
        # ====================================================================
        # 7. Summary
        # ====================================================================
        log(f"\n{'='*80}")
        if all_checks_pass:
            log("✅ ALL CHECKS PASSED - Data is consistent!")
            log(f"\n📊 Summary:")
            log(f"   • {valid_vouchers:,} vouchers synced to Actual Budget")
            log(f"   • {ignored_vouchers:,} vouchers ignored (Geldtransit/Durchlaufende)")
            log(f"   • {total_txn_count:,} total transactions in Actual Budget")
        else:
            log("❌ SOME CHECKS FAILED - Data inconsistency detected!")
            log("\nRecommended actions:")
            log("   1. Review the mismatches above")
            log("   2. Run: python3 reset_sync.py --yes")
            log("   3. Delete all transactions/categories in Actual Budget")
            log("   4. Run: python3 sync_from_cache.py")
        log("="*80 + "\n")
        
        # Send email report if there are inconsistencies or if always requested
        if not all_checks_pass or send_email_always:
            log("📧 Sending email report...")
            email_notifier = EmailNotifier.from_config(config)
            report_text = output_buffer.getvalue()
            if email_notifier.send_consistency_report(report_text, all_checks_pass):
                log("✅ Email report sent successfully")
            else:
                log("⚠️  Failed to send email report")
        
        return all_checks_pass
    
    conn.close()


if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='Verify sync consistency between SevDesk and Actual Budget')
    parser.add_argument('--send-email', action='store_true', 
                       help='Send email report even if all checks pass')
    args = parser.parse_args()
    
    try:
        # Pass the send_email flag to the function
        success = verify_sync_consistency(send_email_always=args.send_email)
        sys.exit(0 if success else 1)
    except Exception as e:
        logger.error(f"\n❌ Error during verification: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
