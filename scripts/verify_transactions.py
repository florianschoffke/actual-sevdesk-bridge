#!/usr/bin/env python3
"""
Verify transaction data quality after sync
"""
import sys
from src.config.settings import Config
from src.api.actual import ActualBudgetClient

def main():
    config = Config()
    
    print("🔍 Connecting to Actual Budget...")
    
    with ActualBudgetClient(
        config.actual_url,
        config.actual_password,
        config.actual_file_id,
        config.actual_verify_ssl
    ) as actual:
        from actual.database import Transactions, Categories
        from sqlalchemy import select
        
        # Get SevDesk transactions
        stmt = select(Transactions).where(
            Transactions.financial_id.like('sevdesk_voucher_%')
        )
        results = actual._actual.session.execute(stmt).scalars().all()
        
        total = len(results)
        if total == 0:
            print("❌ No SevDesk transactions found!")
            return 1
        
        empty_notes = sum(1 for t in results if not t.notes or t.notes == '')
        with_notes = sum(1 for t in results if t.notes and t.notes != '')
        with_category = sum(1 for t in results if t.category_id)
        
        print(f'\n📊 SevDesk Transaction Statistics:')
        print(f'   Total: {total}')
        print(f'   ✅ Empty notes: {empty_notes} ({empty_notes/total*100:.0f}%)')
        print(f'   ⚠️  With notes: {with_notes}')
        print(f'   ✅ With category: {with_category} ({with_category/total*100:.0f}%)')
        print()
        
        # Get category names
        cat_stmt = select(Categories)
        categories = {c.id: c.name for c in actual._actual.session.execute(cat_stmt).scalars().all()}
        
        # Get account names
        accounts = actual.get_accounts()
        account_names = {a['id']: a['name'] for a in accounts}
        
        # Sample transactions
        print('📝 Sample Transactions:')
        for t in sorted(results, key=lambda x: x.date)[:5]:
            cat_name = categories.get(t.category_id, 'NO CATEGORY') if t.category_id else 'NO CATEGORY'
            notes_display = '✅ (empty)' if not t.notes or t.notes == '' else f'❌ "{t.notes}"'
            cat_display = f'✅ {cat_name}' if t.category_id else '❌'
            acct_name = account_names.get(t.acct, 'UNKNOWN')
            print(f'  {t.date}: € {t.amount/100:7.2f} - Notes: {notes_display} - Category: {cat_display}')
            print(f'           Account: {acct_name} - Payee: {t.imported_description}')
        
        print()
        
        # Account distribution
        print('🏦 Account Distribution:')
        account_counts = {}
        for t in results:
            acct_name = account_names.get(t.acct, 'UNKNOWN')
            account_counts[acct_name] = account_counts.get(acct_name, 0) + 1
        
        for acct_name, count in sorted(account_counts.items(), key=lambda x: x[1], reverse=True):
            print(f'   {acct_name}: {count} transactions')
        
        # Check for issues
        issues = []
        if with_notes > 0:
            issues.append(f"❌ {with_notes} transactions have notes (should be empty)")
        if with_category < total:
            issues.append(f"⚠️  {total - with_category} transactions missing category")
        
        if issues:
            print('\n⚠️  Issues Found:')
            for issue in issues:
                print(f'   {issue}')
            return 1
        else:
            print('\n✅ All checks passed!')
            return 0

if __name__ == '__main__':
    sys.exit(main())
