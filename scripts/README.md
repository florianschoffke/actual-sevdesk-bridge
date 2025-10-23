# Utility Scripts

This directory contains utility and maintenance scripts for the Actual-SevDesk Bridge.

## Maintenance Scripts

### `reset_sync.py`
**Purpose:** Reset sync state to start fresh  
**Usage:** `python scripts/reset_sync.py`  
**Use when:** You want to re-sync all data from scratch

### `reconcile_vouchers.py`
**Purpose:** Reconcile vouchers between SevDesk and Actual Budget  
**Usage:** `python scripts/reconcile_vouchers.py`  
**Use when:** You need to clean up orphaned transactions

### `sync_from_cache.py`
**Purpose:** Re-sync from cached SevDesk data without fetching from API  
**Usage:** `python scripts/sync_from_cache.py`  
**Use when:** Testing sync logic without hitting SevDesk API rate limits

## Migration Scripts

### `migrate_durchlaufende.py`
**Purpose:** Migrate "durchlaufende Posten" (pass-through items)  
**Usage:** `python scripts/migrate_durchlaufende.py`  
**Use when:** One-time migration needed

### `enable_carryover.py`
**Purpose:** Enable carryover functionality in Actual Budget  
**Usage:** `python scripts/enable_carryover.py`  
**Use when:** Setting up budget carryover feature

## Verification Scripts

### `verify_sync.py`
**Purpose:** Verify sync integrity between SevDesk and Actual Budget  
**Usage:** `python scripts/verify_sync.py`  
**Use when:** Checking if data is correctly synced

### `verify_transactions.py`
**Purpose:** Verify transaction data consistency  
**Usage:** `python scripts/verify_transactions.py`  
**Use when:** Debugging transaction issues

### `check_actual_transactions.py`
**Purpose:** Check transaction data in Actual Budget  
**Usage:** `python scripts/check_actual_transactions.py`  
**Use when:** Inspecting Actual Budget transactions

## Testing Scripts

### `test_consistency_email.py`
**Purpose:** Test email notification system  
**Usage:** `python scripts/test_consistency_email.py`  
**Use when:** Verifying email notifications work correctly

---

**Note:** Most users won't need these scripts. They're primarily for:
- Troubleshooting sync issues
- One-time migrations
- Development and testing
- Manual data verification
