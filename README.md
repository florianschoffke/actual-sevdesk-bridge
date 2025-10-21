# SevDesk to Actual Budget Bridge

A Python pipeline that synchronizes financial data from SevDesk to Actual Budget.

## � Quick Start

### Docker Deployment (Recommended for Synology NAS)

```bash
# 1. Clone repository
git clone https://github.com/florianschoffke/actual-sevdesk-bridge.git
cd actual-sevdesk-bridge

# 2. Configure
cp .env.example .env
# Edit .env with your credentials

# 3. Run with Docker Compose
docker-compose up -d

# 4. Check logs
docker-compose logs -f
```

**📖 See [DOCKER_DEPLOYMENT.md](DOCKER_DEPLOYMENT.md) for detailed Synology NAS deployment instructions.**

### Local Installation

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Configure
cp .env.example .env
# Edit .env with your SevDesk API key and Actual Budget credentials

# 3. Run sync
python3 main.py sync-all

# 4. Verify consistency
python3 verify_sync.py
```

## �🔄 Pipeline Architecture

This project implements a **3-stage sync pipeline**:

### Stage 1: Account Synchronization
- **Read** accounts from SevDesk
- **Create** matching accounts in Actual Budget (if they don't exist)
- **Track** account mappings by ID
- **Result**: Every SevDesk account has a corresponding Actual account

### Stage 2: Category Synchronization  
- **Read** cost centers (Kostenstellen) from SevDesk
- **Create** matching categories in Actual Budget
- **Allow** category group assignment in Actual (configurable)
- **Track** category mappings by ID
- **Result**: Every SevDesk cost center has a corresponding Actual category

### Stage 3: Voucher Synchronization
- **Read** booked vouchers from SevDesk
- **Create** transactions in Actual Budget
- **Link** to synced accounts and categories using IDs
- **Track** synced transactions to avoid duplicates
- **Result**: All SevDesk vouchers become Actual transactions

## 📁 Project Structure

```
actual-sevdesk-bridge/
├── main.py                # CLI entry point
├── requirements.txt       # Python dependencies
├── .env                   # Configuration (not in git)
├── .env.example          # Example configuration
├── data/                  # SQLite database
│   └── sync_state.db     # Account, category, transaction mappings
└── src/
    ├── api/
    │   ├── sevdesk.py    # SevDesk API client (READ)
    │   └── actual.py     # Actual Budget API client (WRITE)
    ├── storage/
    │   └── database.py   # State tracking & ID mappings
    └── config/
        └── settings.py   # Configuration management
```

## 🎯 Design Principles

1. **ID-based Linking**: All mappings use IDs (not names) for reliability
2. **Separate Stages**: Each stage can run independently
3. **One-way Sync**: SevDesk → Actual Budget only (SevDesk is source of truth)
4. **State Tracking**: SQLite database prevents duplicate syncs
5. **Idempotent**: Safe to run multiple times (won't create duplicates)

## 🚀 Quick Start

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Configure
cp .env.example .env
# Edit .env with your SevDesk API key and Actual Budget credentials

# 3. Run each stage
python main.py sync-accounts --dry-run    # Stage 1: Preview accounts
python main.py sync-accounts              # Stage 1: Sync accounts

python main.py sync-categories --dry-run  # Stage 2: Preview categories
python main.py sync-categories            # Stage 2: Sync categories

python main.py sync-vouchers --dry-run --limit 10   # Stage 3: Preview vouchers
python main.py sync-vouchers --limit 50             # Stage 3: Sync vouchers

# 4. View sync history
python main.py history

# 5. Reset if needed
python main.py reset --confirm
```

## 📋 Available Commands

### Stage 1: Accounts
```bash
python main.py sync-accounts [--dry-run]
```
Syncs SevDesk accounts to Actual Budget accounts.

### Stage 2: Categories
```bash
python main.py sync-categories [--dry-run]
```
Syncs SevDesk cost centers to Actual Budget categories.

**🔄 Carryover Feature**: New categories automatically have carryover enabled for their first month with transactions. This allows unspent budget to roll over to the next month. See [CARRYOVER.md](CARRYOVER.md) for details.

To enable carryover for all existing categories (one-time):
```bash
python3 enable_carryover.py

# Or if you need to disable SSL verification:
python3 enable_carryover.py --no-verify-ssl
```

### Stage 3: Vouchers
```bash
python main.py sync-vouchers [--dry-run] [--limit N]
```
Syncs SevDesk vouchers to Actual Budget transactions.

Options:
- `--dry-run`: Preview without making changes
- `--limit N`: Sync only N most recent vouchers

### Reconciliation
```bash
python main.py reconcile [--dry-run]
```
Finds and removes transactions for vouchers that were unbooked or deleted in SevDesk.

Use this command to clean up orphaned transactions:
- After unbooking vouchers in SevDesk
- As part of weekly maintenance
- Before important reports

**Recommended:** Always run with `--dry-run` first to preview changes.

### Utilities
```bash
python main.py history          # Show sync history
python main.py failed           # Show failed vouchers
python main.py reset --confirm  # Clear all mappings (dangerous!)
```

## ⚙️ Configuration

See `.env.example` for all options. Key settings:

```env
# SevDesk
SEVDESK_API_KEY=your_api_key

# Actual Budget
ACTUAL_BUDGET_URL=https://your-server.com
ACTUAL_BUDGET_PASSWORD=your_password
ACTUAL_BUDGET_FILE_ID=My Finances

# Sync Settings
DEFAULT_VOUCHER_ACCOUNT=Postbank
SYNC_DAYS_BACK=90
SYNC_STATUS=1000  # 1000=Paid vouchers only
```

## 🗄️ Database Schema

The SQLite database tracks 3 types of mappings:

### account_mappings
```
sevdesk_account_id → actual_account_id
```

### category_mappings
```
sevdesk_category_id (cost center) → actual_category_id
```

### transaction_mappings
```
sevdesk_voucher_id → actual_transaction_id
```

## 🔍 How It Works

### Stage 1: Account Sync
1. Fetch all accounts from SevDesk (`/CheckAccount`)
2. Fetch all accounts from Actual Budget
3. For each SevDesk account:
   - Check if mapping exists in database
   - If not, find by name in Actual or create new account
   - Save mapping: `sevdesk_account_id → actual_account_id`

### Stage 2: Category Sync
1. Fetch all cost centers from SevDesk (`/CostCentre`)
2. Fetch all categories from Actual Budget
3. For each SevDesk cost center:
   - Check if mapping exists in database
   - If not, find by name in Actual or create new category
   - Save mapping: `sevdesk_category_id → actual_category_id`

### Stage 3: Voucher Sync
1. Fetch vouchers from SevDesk (`/Voucher`)
2. For each voucher:
   - Check if already synced (database lookup)
   - Skip if has Geldtransit accounting type
   - Look up account mapping (from Stage 1)
   - Look up category mapping (from Stage 2)
   - Create transaction in Actual Budget
   - Save mapping: `voucher_id → transaction_id`

## 🛡️ Safety Features

- **Dry-run mode**: Preview before syncing
- **Duplicate prevention**: Database tracks what's already synced
- **ID-based linking**: Immune to name changes
- **Geldtransit filtering**: Skips transfer vouchers (accounting type 40)
- **Sync history**: Audit trail of all operations
- **Email notifications**: Automatic email alerts for validation failures (see [EMAIL_NOTIFICATIONS.md](EMAIL_NOTIFICATIONS.md))
- **Smart re-validation**: Invalid vouchers automatically re-checked on each sync
- **Voucher caching**: Fast incremental syncs using local cache

## 📈 Roadmap

### ✅ Phase 1: Core Pipeline (Current)
- [x] SevDesk API client
- [x] Actual Budget API client
- [x] Account sync
- [x] Category sync
- [x] Voucher sync
- [x] State database
- [x] CLI interface

### 🔄 Phase 2: Enhanced Features
- [ ] Better category group management
- [ ] Account mapping configuration
- [ ] Transfer handling (Geldtransit)
- [ ] Better error handling & retry logic
- [ ] Progress bars & better output

### 📦 Phase 3: Deployment
- [ ] Docker containerization
- [ ] Cron job for scheduled sync
- [ ] Health monitoring
- [ ] Alerting on failures

## 🐛 Troubleshooting

### "No accounts found"
Run Stage 1 first: `python main.py sync-accounts`

### "Category not mapped"
Run Stage 2 first: `python main.py sync-categories`

### "Already synced"
The voucher is already in the database. Use `reset` to re-sync.

### Reset and start over
```bash
python main.py reset --confirm
python main.py sync-accounts
python main.py sync-categories
python main.py sync-vouchers
```

## 📝 Development

```bash
# Run with verbose logging
LOG_LEVEL=DEBUG python main.py sync-vouchers --dry-run

# Check database directly
sqlite3 data/sync_state.db "SELECT * FROM account_mappings;"
sqlite3 data/sync_state.db "SELECT COUNT(*) FROM transaction_mappings;"
```

## 📄 License

MIT License - See LICENSE file for details.
