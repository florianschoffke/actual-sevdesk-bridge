#!/usr/bin/env python3
"""Check what Florian Schoffke transactions exist in Actual Budget."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from src.config import get_config
from src.api.actual import ActualBudgetClient
from src.storage import Database

config = get_config()
db = Database(config.db_path)

print("🔍 Checking Florian Schoffke transactions in Actual Budget...")
print("=" * 60)

with ActualBudgetClient(
    config.actual_url,
    config.actual_password,
    config.actual_file_id,
    config.actual_verify_ssl
) as actual:
    
    # Get the account
    account = actual.get_or_create_account(config.actual_account_name, offbudget=False)
    account_id = account['id']
    print(f"Account: {account['name']} ({account_id})\n")
    
    # Get all transactions
    from actual.database import Transactions
    from sqlalchemy import select, and_
    
    stmt = select(Transactions).where(
        and_(
            Transactions.acct == account_id,
            Transactions.tombstone == 0
        )
    )
    all_transactions = actual._actual.session.execute(stmt).scalars().all()
    
    print(f"Total transactions in Actual: {len(all_transactions)}\n")
    
    # Search for transactions with €250 amount (Florian Schoffke vouchers)
    amount_250_transactions = [t for t in all_transactions if abs(t.amount) == 25000]
    print(f"Transactions with €250 amount: {len(amount_250_transactions)}\n")
    
    if amount_250_transactions:
        print("€250 transactions:")
        print("-" * 80)
        for t in sorted(amount_250_transactions, key=lambda x: x.date, reverse=True):
            date_str = str(t.date)[:10]
            amount = t.amount / 100
            imported_id = (t.financial_id or "NO_IMPORTED_ID")[:30]
            notes = (t.notes or "")[:20]
            cat_id = str(t.category)[:36] if t.category else "UNCATEGORIZED"
            print(f"  {date_str} | €{amount:>7.2f} | {cat_id:<36} | {imported_id}")
    
    print("\n" + "=" * 80)
    # Filter for Florian Schoffke (cost center ID 180731)
    # Get category mapping
    category_mappings = {m['sevdesk_category_id']: m['actual_category_id'] for m in db.get_all_category_mappings()}
    florian_category_id = category_mappings.get('180731')
    
    print(f"Florian Schoffke category ID in Actual: {florian_category_id}")
    
    if florian_category_id:
        florian_transactions = [t for t in all_transactions if t.category == florian_category_id]
        print(f"Florian Schoffke transactions: {len(florian_transactions)}\n")
        
        if florian_transactions:
            print("Transactions found:")
            print("-" * 60)
            for t in sorted(florian_transactions, key=lambda x: x.date, reverse=True):
                date_str = str(t.date)[:10]
                amount = t.amount / 100
                imported_id = t.financial_id or "NO_IMPORTED_ID"
                notes = t.notes or ""
                print(f"  {date_str} | €{amount:>7.2f} | {imported_id[:30]:<30} | {notes[:30]}")
