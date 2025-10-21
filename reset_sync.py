#!/usr/bin/env python3
"""
Reset sync state to prepare for fresh sync.
This clears transaction mappings, category mappings, and sync history.
Note: Does NOT delete data from Actual Budget - do that manually first!
      Does NOT delete voucher cache - keeping it for fast re-sync.
"""

import sqlite3
import sys
from datetime import datetime

def reset_sync_state():
    """Clear sync state from the database while preserving cache."""
    conn = sqlite3.connect('data/sync_state.db')
    cursor = conn.cursor()
    
    # Count existing data
    cursor.execute('SELECT COUNT(*) FROM transaction_mappings')
    transaction_count = cursor.fetchone()[0]
    
    cursor.execute('SELECT COUNT(*) FROM category_mappings')
    category_count = cursor.fetchone()[0]
    
    cursor.execute('SELECT COUNT(*) FROM sync_history')
    history_count = cursor.fetchone()[0]
    
    cursor.execute('SELECT COUNT(*) FROM failed_vouchers')
    failed_count = cursor.fetchone()[0]
    
    if transaction_count == 0 and category_count == 0:
        print('ℹ️  Nothing to reset - database is already clean.')
        conn.close()
        return
    
    print('📋 Current database state:')
    print(f'   • Transaction mappings: {transaction_count}')
    print(f'   • Category mappings: {category_count}')
    print(f'   • Sync history: {history_count}')
    print(f'   • Failed vouchers: {failed_count}')
    print()
    
    # Confirm
    if '--yes' not in sys.argv:
        response = input('Reset sync state (clear all mappings)? (yes/no): ').strip().lower()
        if response != 'yes':
            print('❌ Cancelled')
            conn.close()
            return
    
    # Create backup first
    backup_file = f'data/sync_state.db.backup_{datetime.now().strftime("%Y%m%d_%H%M%S")}'
    print(f'\n💾 Creating backup: {backup_file}')
    cursor.execute(f"VACUUM INTO '{backup_file}'")
    
    # Delete mappings and history
    cursor.execute('DELETE FROM transaction_mappings')
    cursor.execute('DELETE FROM category_mappings')
    cursor.execute('DELETE FROM sync_history')
    cursor.execute('DELETE FROM failed_vouchers')
    conn.commit()
    
    print('\n✅ Reset complete!')
    print(f'   • Deleted {transaction_count} transaction mappings')
    print(f'   • Deleted {category_count} category mappings')
    print(f'   • Deleted {history_count} sync history entries')
    print(f'   • Deleted {failed_count} failed voucher records')
    
    # Show what's preserved
    cursor.execute('SELECT COUNT(*) FROM voucher_cache')
    cache_count = cursor.fetchone()[0]
    print(f'\n✅ Preserved voucher cache: {cache_count} vouchers')
    
    print()
    print('⚠️  Important: This does NOT delete data from Actual Budget!')
    print('   Before running sync_from_cache.py:')
    print('   1. Manually delete all transactions in Actual Budget UI')
    print('   2. Manually delete all categories in Actual Budget UI')
    print('   3. Then run: python3 sync_from_cache.py')
    
    conn.close()

if __name__ == '__main__':
    reset_sync_state()
