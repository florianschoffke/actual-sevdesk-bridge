#!/usr/bin/env python3
"""
Migration: Re-enable Durchlaufende Posten vouchers that have a cost centre.

This migration clears the "ignored" flag for vouchers that:
- Are marked as "Durchlaufende Posten" (accounting type 39)
- Have a cost centre assigned
- Should now be synced according to new logic
"""
import sqlite3
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

from src.config import get_config


def migrate():
    """Clear ignored flag for Durchlaufende Posten with cost centres."""
    config = get_config()
    db_path = config.db_path
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    print("🔍 Checking for Durchlaufende Posten vouchers with cost centres...")
    
    # Find vouchers that:
    # 1. Are marked as ignored with "Durchlaufende Posten" reason
    # 2. Have a cost centre in their voucher data
    cursor.execute('''
        SELECT 
            tm.sevdesk_id,
            json_extract(vc.voucher_data, '$.costCentre.id') as cost_centre_id,
            vc.voucher_number,
            vc.voucher_date,
            vc.amount
        FROM transaction_mappings tm
        JOIN voucher_cache vc ON tm.sevdesk_id = 'voucher_' || vc.id
        WHERE tm.ignored = 1 
        AND tm.actual_id = 'Durchlaufende Posten'
        AND json_extract(vc.voucher_data, '$.costCentre.id') IS NOT NULL
    ''')
    
    vouchers_to_clear = cursor.fetchall()
    
    if not vouchers_to_clear:
        print("✅ No vouchers need migration")
        conn.close()
        return
    
    print(f"📋 Found {len(vouchers_to_clear)} Durchlaufende Posten vouchers with cost centres:")
    for sevdesk_id, cost_centre_id, voucher_number, voucher_date, amount in vouchers_to_clear:
        print(f"  - {sevdesk_id}: €{amount} on {voucher_date} (cost centre: {cost_centre_id})")
    
    print("\n❓ These vouchers will be re-synced on next sync run.")
    print("   They were previously ignored but now have cost centres.")
    
    response = input("\nContinue with migration? (yes/no): ")
    if response.lower() not in ['yes', 'y']:
        print("❌ Migration cancelled")
        conn.close()
        return
    
    # Delete the ignored mappings so they can be re-synced
    sevdesk_ids = [v[0] for v in vouchers_to_clear]
    placeholders = ','.join('?' * len(sevdesk_ids))
    
    cursor.execute(f'''
        DELETE FROM transaction_mappings
        WHERE sevdesk_id IN ({placeholders})
    ''', sevdesk_ids)
    
    conn.commit()
    
    print(f"\n✅ Migration complete!")
    print(f"   Cleared {len(vouchers_to_clear)} voucher mappings")
    print(f"   These will be synced on next run")
    
    conn.close()


if __name__ == "__main__":
    try:
        migrate()
    except Exception as e:
        print(f"❌ Migration failed: {e}")
        sys.exit(1)
