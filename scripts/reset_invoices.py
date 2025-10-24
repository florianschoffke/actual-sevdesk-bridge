#!/usr/bin/env python3
"""
Reset invoice sync state.
Clears invoice mappings so they can be re-synced with correct amounts.
You need to manually delete invoice transactions from Actual Budget first!
"""

import sqlite3
import sys

def reset_invoices():
    """Clear invoice sync state from the database."""
    conn = sqlite3.connect('data/sync_state.db')
    cursor = conn.cursor()
    
    # Count existing invoice mappings
    cursor.execute("SELECT COUNT(*) FROM invoice_mappings")
    invoice_count = cursor.fetchone()[0]
    
    if invoice_count == 0:
        print('ℹ️  No invoice mappings to reset.')
        conn.close()
        return
    
    print('📋 Current state:')
    print(f'   • Invoice mappings: {invoice_count}')
    print()
    print('⚠️  IMPORTANT:')
    print('   1. First, manually delete invoice transactions from Actual Budget')
    print('   2. Then run this script to clear the mappings')
    print('   3. Next sync will recreate them with correct amounts')
    print()
    
    # Confirm
    if '--yes' not in sys.argv:
        response = input('Clear invoice mappings? (yes/no): ').strip().lower()
        if response != 'yes':
            print('❌ Cancelled')
            conn.close()
            return
    
    # Clear invoice mappings
    cursor.execute('DELETE FROM invoice_mappings')
    conn.commit()
    
    print(f'✅ Cleared {invoice_count} invoice mappings')
    print()
    print('Next steps:')
    print('1. Make sure you deleted invoice transactions from Actual Budget')
    print('2. Run the sync again to recreate them with correct amounts')
    
    conn.close()

if __name__ == '__main__':
    reset_invoices()
