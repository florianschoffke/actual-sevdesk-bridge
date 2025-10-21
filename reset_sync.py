#!/usr/bin/env python3
"""
Reset transaction sync mappings.
This clears the database so vouchers can be synced again.
Note: Does NOT delete transactions from Actual Budget - do that manually first!
"""

import sqlite3
import sys

def reset_transaction_mappings():
    """Clear all transaction mappings from the database."""
    conn = sqlite3.connect('data/sync_state.db')
    cursor = conn.cursor()
    
    # Count existing mappings
    cursor.execute('SELECT COUNT(*) FROM transaction_mappings')
    count_before = cursor.fetchone()[0]
    
    if count_before == 0:
        print('ℹ️  No transaction mappings to clear.')
        conn.close()
        return
    
    print(f'Found {count_before} transaction mapping(s)')
    
    # Confirm
    if '--yes' not in sys.argv:
        response = input('Clear all transaction mappings? (yes/no): ').strip().lower()
        if response != 'yes':
            print('❌ Cancelled')
            conn.close()
            return
    
    # Delete all transaction mappings
    cursor.execute('DELETE FROM transaction_mappings')
    conn.commit()
    
    cursor.execute('SELECT COUNT(*) FROM transaction_mappings')
    count_after = cursor.fetchone()[0]
    
    print(f'✅ Deleted {count_before - count_after} transaction mapping(s)')
    print()
    print('⚠️  Important: This does NOT delete transactions from Actual Budget!')
    print('   You must manually delete them in the Actual Budget UI.')
    
    conn.close()

if __name__ == '__main__':
    reset_transaction_mappings()
