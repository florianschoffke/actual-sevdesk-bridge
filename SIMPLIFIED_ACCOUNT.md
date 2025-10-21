# Simplified Account Model

## Changes Made

### Overview
The bridge now uses a **single configurable account** instead of syncing multiple accounts from SevDesk. This simplifies the architecture because:

1. **Focus on amounts, not locations**: We only track how much money is spent/received, not which bank account it's in
2. **Simpler sync process**: No need for complex account mapping logic
3. **Cleaner architecture**: One account = one source of truth

### Configuration

Add to your `.env` file:
```bash
ACTUAL_ACCOUNT_NAME="EGB Funds"
```

Default value is "EGB Funds" if not specified.

### What Changed

#### 1. Removed Account Sync Stage
- **Before**: Stage 1 (Accounts) → Stage 2 (Categories) → Stage 3 (Vouchers)
- **After**: Stage 1 (Categories) → Stage 2 (Vouchers)

#### 2. Single Account Creation
- On first sync, the bridge creates or finds the account named `ACTUAL_ACCOUNT_NAME`
- All transactions are imported to this single account
- Account is created automatically if it doesn't exist

#### 3. Updated Files

**`src/config/settings.py`**:
- Added `actual_account_name` configuration (default: "EGB Funds")
- Removed `default_voucher_account` (was "Postbank")

**`src/api/actual.py`**:
- Added `get_or_create_account()` method
- Creates account if it doesn't exist, returns existing if found

**`src/sync/vouchers.py`**:
- Uses `get_or_create_account()` instead of querying all accounts
- All transactions go to the configured account
- Updated logging to remove "Stage 3" references

**`main.py`**:
- Removed Stage 1 (account sync) from `sync-all` command
- Updated help text: "Sync categories and vouchers"
- Simplified flow to 2 stages

### Usage

```bash
# Sync with default "EGB Funds" account
python3 main.py sync-all

# Sync with custom account name (set in .env)
ACTUAL_ACCOUNT_NAME="My Account"
python3 main.py sync-all

# Sync with limit
python3 main.py sync-all --limit 50
```

### Migration Steps

1. **Flush Actual Budget**: Manually delete all transactions
2. **Delete sync state**: `rm data/sync_state.db`
3. **Configure account name**: Add `ACTUAL_ACCOUNT_NAME` to `.env` (optional)
4. **Run sync**: `python3 main.py sync-all`

The account will be created automatically on first sync.

### Benefits

✅ **Simpler**: One account, less complexity
✅ **Cleaner**: No account mapping logic needed
✅ **Configurable**: Account name can be customized
✅ **Automatic**: Account created on first run
✅ **Focus**: Track expenses/income, not account locations

### Technical Details

- Account is created as an **on-budget** account (not off-budget)
- Account name matching is exact (case-sensitive)
- If account exists with same name, it's reused
- Account ID is stable across syncs (stored in Actual Budget database)
