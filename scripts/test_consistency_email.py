#!/usr/bin/env python3
"""Test consistency check email notification."""
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / 'src'))

from config.settings import get_config
from notifications.email_notifier import EmailNotifier

# Sample report output (simulating a failure)
sample_report = """
================================================================================
🔍 SYNC CONSISTENCY CHECK
================================================================================

📊 Step 1: Voucher Counts
--------------------------------------------------------------------------------
   Total cached vouchers:       4,236
   Valid vouchers (to sync):    4,089
   Ignored vouchers (39/40/81): 147
   Mapped transactions in DB:   4,236

📊 Step 2: Actual Budget Transactions
--------------------------------------------------------------------------------
   Imported transactions:       3,850 (with sevdesk_voucher_* ID)
   Total transactions:          3,850 (including manual)

✅ Step 3: Consistency Check
--------------------------------------------------------------------------------
   ❌ MISMATCH: Valid vouchers (4,089) ≠ Imported transactions (3,850)
      Difference: 239 transactions
   ✅ Total mapped (4,236) = Valid (4,089) + Ignored (147)

📊 Step 4: Amount Verification
--------------------------------------------------------------------------------
   ❌ MISMATCH: 5 out of 100 vouchers have amount differences
      Voucher 123456: Expected 250.00€, Got 245.00€
      Voucher 123457: Expected 100.00€, Got 95.00€
      Voucher 123458: Expected 500.00€, Got 495.00€
      Voucher 123459: Expected 75.00€, Got 70.00€
      Voucher 123460: Expected 300.00€, Got 295.00€

📊 Step 5: Duplicate Detection
--------------------------------------------------------------------------------
   ❌ WARNING: 12 duplicate imported_ids found:
      sevdesk_voucher_123461: 2 transactions
      sevdesk_voucher_123462: 2 transactions
      sevdesk_voucher_123463: 2 transactions
      sevdesk_voucher_123464: 2 transactions
      sevdesk_voucher_123465: 2 transactions

📊 Step 6: Orphaned Mappings
--------------------------------------------------------------------------------
   ⚠️  WARNING: 147 mappings without corresponding vouchers
      (This can happen if vouchers are deleted from cache)

================================================================================
❌ SOME CHECKS FAILED - Data inconsistency detected!

Recommended actions:
   1. Review the mismatches above
   2. Run: python3 reset_sync.py --yes
   3. Delete all transactions/categories in Actual Budget
   4. Run: python3 sync_from_cache.py
================================================================================
"""

if __name__ == '__main__':
    config = get_config()
    email_notifier = EmailNotifier.from_config(config)
    
    print("📧 Testing consistency check email with simulated failures...")
    
    if email_notifier.send_consistency_report(sample_report, checks_passed=False):
        print("✅ Test email sent successfully!")
    else:
        print("❌ Failed to send test email")
