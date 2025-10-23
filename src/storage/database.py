"""Database for storing sync state."""
import sqlite3
from pathlib import Path
from typing import Dict, List, Optional, Any
from datetime import datetime


class Database:
    """SQLite database for sync state management."""
    
    def __init__(self, db_path: Path):
        """
        Initialize database connection.
        
        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_database()
    
    def _init_database(self):
        """Create database tables if they don't exist."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Account mappings (SevDesk Accounts -> Actual Accounts)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS account_mappings (
                sevdesk_account_id TEXT PRIMARY KEY,
                actual_account_id TEXT NOT NULL,
                sevdesk_account_name TEXT,
                actual_account_name TEXT,
                created_at TEXT NOT NULL
            )
        ''')
        
        # Category mappings (Cost Centers -> Actual Categories)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS category_mappings (
                sevdesk_category_id TEXT PRIMARY KEY,
                actual_category_id TEXT NOT NULL,
                sevdesk_category_name TEXT,
                actual_category_name TEXT,
                created_at TEXT NOT NULL
            )
        ''')
        
        # Transaction mappings (Vouchers -> Actual Transactions)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS transaction_mappings (
                sevdesk_id TEXT PRIMARY KEY,
                actual_id TEXT NOT NULL,
                sevdesk_value_date TEXT,
                sevdesk_amount REAL,
                sevdesk_update_timestamp TEXT,
                synced_at TEXT NOT NULL,
                ignored INTEGER DEFAULT 0
            )
        ''')
        
        # Failed vouchers (vouchers that failed validation)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS failed_vouchers (
                sevdesk_voucher_id TEXT PRIMARY KEY,
                voucher_number TEXT,
                voucher_date TEXT,
                amount REAL,
                voucher_type TEXT,
                failure_reason TEXT NOT NULL,
                failed_at TEXT NOT NULL,
                retry_count INTEGER DEFAULT 0
            )
        ''')
        
        # Sync history
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS sync_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sync_type TEXT NOT NULL,
                started_at TEXT NOT NULL,
                completed_at TEXT,
                status TEXT NOT NULL,
                items_processed INTEGER DEFAULT 0,
                items_synced INTEGER DEFAULT 0,
                items_failed INTEGER DEFAULT 0,
                error_message TEXT
            )
        ''')
        
        # Voucher cache (stores voucher metadata)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS voucher_cache (
                id TEXT PRIMARY KEY,
                voucher_number TEXT,
                voucher_date TEXT,
                status TEXT,
                amount REAL,
                cost_center_id TEXT,
                cost_center_name TEXT,
                supplier_name TEXT,
                create_timestamp TEXT,
                update_timestamp TEXT,
                voucher_data TEXT,
                cached_at TEXT NOT NULL,
                edited INTEGER DEFAULT 0,
                is_valid INTEGER DEFAULT NULL,
                validation_reason TEXT,
                last_validated_at TEXT
            )
        ''')
        
        # Create index on update_timestamp for efficient incremental queries
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_voucher_update 
            ON voucher_cache(update_timestamp)
        ''')
        
        # Create index on edited flag for efficient filtered queries
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_voucher_edited 
            ON voucher_cache(edited)
        ''')
        
        # Voucher positions cache
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS voucher_position_cache (
                id TEXT PRIMARY KEY,
                voucher_id TEXT NOT NULL,
                accounting_type_id TEXT,
                accounting_type_name TEXT,
                sum_net REAL,
                tax_rate REAL,
                comment TEXT,
                position_data TEXT,
                cached_at TEXT NOT NULL,
                FOREIGN KEY (voucher_id) REFERENCES voucher_cache(id)
            )
        ''')
        
        # Create index on voucher_id for efficient position lookups
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_position_voucher 
            ON voucher_position_cache(voucher_id)
        ''')
        
        # Invoice mappings (Invoices -> Actual Transactions)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS invoice_mappings (
                sevdesk_id TEXT PRIMARY KEY,
                actual_id TEXT NOT NULL,
                sevdesk_invoice_date TEXT,
                sevdesk_amount REAL,
                sevdesk_update_timestamp TEXT,
                synced_at TEXT NOT NULL,
                ignored INTEGER DEFAULT 0
            )
        ''')
        
        # Failed invoices (invoices that failed validation)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS failed_invoices (
                sevdesk_invoice_id TEXT PRIMARY KEY,
                invoice_number TEXT,
                invoice_date TEXT,
                amount REAL,
                failure_reason TEXT NOT NULL,
                failed_at TEXT NOT NULL,
                retry_count INTEGER DEFAULT 0
            )
        ''')
        
        # Invoice cache (stores invoice metadata)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS invoice_cache (
                id TEXT PRIMARY KEY,
                invoice_number TEXT,
                invoice_date TEXT,
                status TEXT,
                amount REAL,
                cost_center_id TEXT,
                cost_center_name TEXT,
                contact_name TEXT,
                create_timestamp TEXT,
                update_timestamp TEXT,
                invoice_data TEXT,
                cached_at TEXT NOT NULL,
                is_valid INTEGER DEFAULT NULL,
                validation_reason TEXT,
                last_validated_at TEXT
            )
        ''')
        
        # Create index on update_timestamp for efficient incremental queries
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_invoice_update 
            ON invoice_cache(update_timestamp)
        ''')
        
        # Invoice positions cache
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS invoice_position_cache (
                id TEXT PRIMARY KEY,
                invoice_id TEXT NOT NULL,
                cost_center_id TEXT,
                cost_center_name TEXT,
                sum_net REAL,
                tax_rate REAL,
                text TEXT,
                position_data TEXT,
                cached_at TEXT NOT NULL,
                FOREIGN KEY (invoice_id) REFERENCES invoice_cache(id)
            )
        ''')
        
        # Create index on invoice_id for efficient position lookups
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_position_invoice 
            ON invoice_position_cache(invoice_id)
        ''')
        
        conn.commit()
        conn.close()
    
    # Account Mapping Methods
    
    def save_account_mapping(
        self,
        sevdesk_id: str,
        actual_id: str,
        sevdesk_name: Optional[str] = None,
        actual_name: Optional[str] = None
    ):
        """Save an account mapping."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT OR REPLACE INTO account_mappings
            (sevdesk_account_id, actual_account_id, sevdesk_account_name,
             actual_account_name, created_at)
            VALUES (?, ?, ?, ?, ?)
        ''', (
            sevdesk_id,
            actual_id,
            sevdesk_name,
            actual_name,
            datetime.now().isoformat()
        ))
        
        conn.commit()
        conn.close()
    
    def get_account_mapping(self, sevdesk_id: str) -> Optional[str]:
        """Get Actual account ID for a SevDesk account ID."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT actual_account_id FROM account_mappings
            WHERE sevdesk_account_id = ?
        ''', (sevdesk_id,))
        
        result = cursor.fetchone()
        conn.close()
        
        return result[0] if result else None
    
    def get_all_account_mappings(self) -> List[Dict]:
        """Get all account mappings."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute('SELECT * FROM account_mappings')
        rows = cursor.fetchall()
        conn.close()
        
        return [dict(row) for row in rows]
    
    def update_account_mapping(self, sevdesk_id: str, new_actual_id: str) -> bool:
        """
        Update an existing account mapping with a new Actual Budget account ID.
        
        Args:
            sevdesk_id: SevDesk account ID
            new_actual_id: New Actual Budget account ID
        
        Returns:
            True if updated, False if not found
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            UPDATE account_mappings
            SET actual_account_id = ?
            WHERE sevdesk_account_id = ?
        ''', (new_actual_id, sevdesk_id))
        
        updated = cursor.rowcount > 0
        conn.commit()
        conn.close()
        
        return updated
    
    # Category Mapping Methods
    
    def save_category_mapping(
        self,
        sevdesk_id: str,
        actual_id: str,
        sevdesk_name: Optional[str] = None,
        actual_name: Optional[str] = None
    ):
        """Save a category mapping."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT OR REPLACE INTO category_mappings
            (sevdesk_category_id, actual_category_id, sevdesk_category_name, 
             actual_category_name, created_at)
            VALUES (?, ?, ?, ?, ?)
        ''', (
            sevdesk_id,
            actual_id,
            sevdesk_name,
            actual_name,
            datetime.now().isoformat()
        ))
        
        conn.commit()
        conn.close()
    
    def get_category_mapping(self, sevdesk_id: str) -> Optional[str]:
        """Get Actual category ID for a SevDesk cost center ID."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT actual_category_id FROM category_mappings
            WHERE sevdesk_category_id = ?
        ''', (sevdesk_id,))
        
        result = cursor.fetchone()
        conn.close()
        
        return result[0] if result else None
    
    def get_all_category_mappings(self) -> List[Dict]:
        """Get all category mappings."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute('SELECT * FROM category_mappings')
        rows = cursor.fetchall()
        conn.close()
        
        return [dict(row) for row in rows]
    
    def update_category_mapping(self, sevdesk_id: str, new_actual_id: str) -> bool:
        """
        Update an existing category mapping with a new Actual Budget category ID.
        
        Args:
            sevdesk_id: SevDesk cost center ID
            new_actual_id: New Actual Budget category ID
        
        Returns:
            True if updated, False if not found
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            UPDATE category_mappings
            SET actual_category_id = ?
            WHERE sevdesk_category_id = ?
        ''', (new_actual_id, sevdesk_id))
        
        updated = cursor.rowcount > 0
        conn.commit()
        conn.close()
        
        return updated
    
    # Transaction Mapping Methods
    
    def save_transaction_mapping(
        self,
        sevdesk_id: str,
        actual_id: str,
        sevdesk_value_date: Optional[str] = None,
        sevdesk_amount: Optional[float] = None,
        sevdesk_update_timestamp: Optional[str] = None
    ):
        """Save a transaction mapping."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT OR REPLACE INTO transaction_mappings
            (sevdesk_id, actual_id, sevdesk_value_date, sevdesk_amount,
             sevdesk_update_timestamp, synced_at)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (
            sevdesk_id,
            actual_id,
            sevdesk_value_date,
            sevdesk_amount,
            sevdesk_update_timestamp,
            datetime.now().isoformat()
        ))
        
        conn.commit()
        conn.close()
    
    def get_transaction_mapping(self, sevdesk_id: str) -> Optional[Dict]:
        """Get transaction mapping for a SevDesk voucher ID."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT * FROM transaction_mappings
            WHERE sevdesk_id = ?
        ''', (sevdesk_id,))
        
        row = cursor.fetchone()
        conn.close()
        
        return dict(row) if row else None
    
    def get_all_transaction_mappings(self) -> List[Dict]:
        """Get all transaction mappings."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute('SELECT * FROM transaction_mappings')
        rows = cursor.fetchall()
        conn.close()
        
        return [dict(row) for row in rows]
    
    def clear_transaction_mappings(self) -> int:
        """Clear all transaction mappings. Returns number of deleted rows."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('DELETE FROM transaction_mappings')
        deleted = cursor.rowcount
        
        conn.commit()
        conn.close()
        
        return deleted
    
    def delete_transaction_mapping(self, sevdesk_id: str) -> bool:
        """
        Delete a transaction mapping.
        
        Args:
            sevdesk_id: SevDesk voucher ID
        
        Returns:
            True if deleted, False if not found
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('DELETE FROM transaction_mappings WHERE sevdesk_id = ?', (sevdesk_id,))
        deleted = cursor.rowcount > 0
        
        conn.commit()
        conn.close()
        
        return deleted
    
    def mark_voucher_ignored(
        self,
        sevdesk_id: str,
        reason: str
    ):
        """
        Mark a voucher as ignored (won't be synced to Actual Budget).
        
        Args:
            sevdesk_id: SevDesk voucher ID
            reason: Reason for ignoring (e.g., "Geldtransit", "Durchlaufende Posten")
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT OR REPLACE INTO transaction_mappings
            (sevdesk_id, actual_id, ignored, synced_at)
            VALUES (?, ?, 1, ?)
        ''', (
            sevdesk_id,
            reason,  # Store reason in actual_id field
            datetime.now().isoformat()
        ))
        
        conn.commit()
        conn.close()
    
    def is_voucher_ignored(self, sevdesk_id: str) -> bool:
        """Check if a voucher is marked as ignored."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT ignored FROM transaction_mappings
            WHERE sevdesk_id = ? AND ignored = 1
        ''', (sevdesk_id,))
        
        result = cursor.fetchone()
        conn.close()
        
        return result is not None
    
    # Failed Voucher Methods
    
    def save_failed_voucher(
        self,
        voucher_id: str,
        voucher_date: str,
        amount: float,
        voucher_type: str,
        failure_reason: str,
        voucher_number: str = None
    ):
        """Save a voucher that failed validation."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Check if already exists
        cursor.execute('SELECT retry_count FROM failed_vouchers WHERE sevdesk_voucher_id = ?', (voucher_id,))
        existing = cursor.fetchone()
        
        if existing:
            # Update retry count and info
            cursor.execute('''
                UPDATE failed_vouchers
                SET voucher_number = ?,
                    failure_reason = ?,
                    failed_at = ?,
                    retry_count = retry_count + 1
                WHERE sevdesk_voucher_id = ?
            ''', (voucher_number, failure_reason, datetime.now().isoformat(), voucher_id))
        else:
            # Insert new
            cursor.execute('''
                INSERT INTO failed_vouchers 
                (sevdesk_voucher_id, voucher_number, voucher_date, amount, voucher_type, failure_reason, failed_at, retry_count)
                VALUES (?, ?, ?, ?, ?, ?, ?, 0)
            ''', (voucher_id, voucher_number, voucher_date, amount, voucher_type, failure_reason, datetime.now().isoformat()))
        
        conn.commit()
        conn.close()
    
    def is_failed_voucher(self, voucher_id: str) -> bool:
        """Check if a voucher has failed validation before."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('SELECT 1 FROM failed_vouchers WHERE sevdesk_voucher_id = ?', (voucher_id,))
        exists = cursor.fetchone() is not None
        
        conn.close()
        return exists
    
    def get_failed_vouchers(self, limit: int = 100) -> List[Dict]:
        """Get list of failed vouchers."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT * FROM failed_vouchers
            ORDER BY failed_at DESC
            LIMIT ?
        ''', (limit,))
        
        rows = cursor.fetchall()
        conn.close()
        
        return [dict(row) for row in rows]
    
    def clear_failed_vouchers(self, voucher_ids: List[str] = None) -> int:
        """
        Clear failed vouchers to allow retry.
        If voucher_ids is None, clears all. Otherwise clears specific IDs.
        Returns number of deleted rows.
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        if voucher_ids:
            placeholders = ','.join('?' * len(voucher_ids))
            cursor.execute(f'DELETE FROM failed_vouchers WHERE sevdesk_voucher_id IN ({placeholders})', voucher_ids)
        else:
            cursor.execute('DELETE FROM failed_vouchers')
        
        deleted = cursor.rowcount
        conn.commit()
        conn.close()
        
        return deleted
    
    # Invoice Mapping Methods
    
    def save_invoice_mapping(
        self,
        sevdesk_id: str,
        actual_id: str,
        invoice_date: Optional[str] = None,
        amount: Optional[float] = None,
        update_timestamp: Optional[str] = None
    ):
        """Save an invoice to transaction mapping."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT OR REPLACE INTO invoice_mappings
            (sevdesk_id, actual_id, sevdesk_invoice_date, sevdesk_amount, 
             sevdesk_update_timestamp, synced_at)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (
            sevdesk_id,
            actual_id,
            invoice_date,
            amount,
            update_timestamp,
            datetime.now().isoformat()
        ))
        
        conn.commit()
        conn.close()
    
    def get_invoice_mapping(self, sevdesk_id: str) -> Optional[Dict]:
        """Get invoice mapping for a SevDesk invoice ID."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT * FROM invoice_mappings
            WHERE sevdesk_id = ?
        ''', (sevdesk_id,))
        
        row = cursor.fetchone()
        conn.close()
        
        return dict(row) if row else None
    
    def get_all_invoice_mappings(self) -> List[Dict]:
        """Get all invoice mappings."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute('SELECT * FROM invoice_mappings')
        rows = cursor.fetchall()
        conn.close()
        
        return [dict(row) for row in rows]
    
    def delete_invoice_mapping(self, sevdesk_id: str) -> bool:
        """
        Delete an invoice mapping.
        
        Args:
            sevdesk_id: SevDesk invoice ID
        
        Returns:
            True if deleted, False if not found
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('DELETE FROM invoice_mappings WHERE sevdesk_id = ?', (sevdesk_id,))
        deleted = cursor.rowcount > 0
        
        conn.commit()
        conn.close()
        
        return deleted
    
    def mark_invoice_ignored(self, sevdesk_id: str, reason: str):
        """Mark an invoice as ignored (won't be synced)."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            UPDATE invoice_mappings
            SET ignored = 1
            WHERE sevdesk_id = ?
        ''', (sevdesk_id,))
        
        conn.commit()
        conn.close()
    
    def is_invoice_ignored(self, sevdesk_id: str) -> bool:
        """Check if an invoice is marked as ignored."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT ignored FROM invoice_mappings
            WHERE sevdesk_id = ?
        ''', (sevdesk_id,))
        
        result = cursor.fetchone()
        conn.close()
        
        return bool(result and result[0]) if result else False
    
    # Sync History Methods
    
    def start_sync(self, sync_type: str) -> int:
        """Start a new sync operation. Returns sync ID."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO sync_history (sync_type, started_at, status)
            VALUES (?, ?, ?)
        ''', (sync_type, datetime.now().isoformat(), 'running'))
        
        sync_id = cursor.lastrowid
        conn.commit()
        conn.close()
        
        return sync_id
    
    def complete_sync(
        self,
        sync_id: int,
        status: str,
        items_processed: int = 0,
        items_synced: int = 0,
        items_failed: int = 0,
        error_message: Optional[str] = None
    ):
        """Complete a sync operation."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            UPDATE sync_history
            SET completed_at = ?,
                status = ?,
                items_processed = ?,
                items_synced = ?,
                items_failed = ?,
                error_message = ?
            WHERE id = ?
        ''', (
            datetime.now().isoformat(),
            status,
            items_processed,
            items_synced,
            items_failed,
            error_message,
            sync_id
        ))
        
        conn.commit()
        conn.close()
    
    def get_sync_history(self, limit: int = 10) -> List[Dict]:
        """Get recent sync history."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT * FROM sync_history
            ORDER BY started_at DESC
            LIMIT ?
        ''', (limit,))
        
        rows = cursor.fetchall()
        conn.close()
        
        return [dict(row) for row in rows]
    
    def get_last_successful_sync(self, sync_type: str) -> Optional[Dict]:
        """Get the last successful sync for a given type."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT * FROM sync_history
            WHERE sync_type = ? AND status = 'completed'
            ORDER BY completed_at DESC
            LIMIT 1
        ''', (sync_type,))
        
        row = cursor.fetchone()
        conn.close()
        
        return dict(row) if row else None

    
    # Voucher Cache Methods
    
    def save_voucher_to_cache(self, voucher: Dict):
        """Save a voucher to the cache."""
        import json
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cost_center = voucher.get('costCentre') or {}
        
        cursor.execute('''
            INSERT OR REPLACE INTO voucher_cache
            (id, voucher_number, voucher_date, status, amount, 
             cost_center_id, cost_center_name, supplier_name,
             create_timestamp, update_timestamp, voucher_data, cached_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            voucher.get('id'),
            voucher.get('voucherNumber'),
            voucher.get('voucherDate'),
            voucher.get('status'),
            float(voucher.get('sumNet', 0) or 0),
            cost_center.get('id') if cost_center else None,
            cost_center.get('name') if cost_center else None,
            voucher.get('supplier', {}).get('name') if voucher.get('supplier') else None,
            voucher.get('createTimestamp'),
            voucher.get('updateTimestamp'),
            json.dumps(voucher),
            datetime.now().isoformat()
        ))
        
        conn.commit()
        conn.close()

    # Voucher Cache Methods
    
    def save_vouchers_to_cache_batch(self, vouchers: List[Dict]):
        """Save multiple vouchers to cache in a batch."""
        import json
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        now = datetime.now().isoformat()
        
        data = []
        for voucher in vouchers:
            cost_center = voucher.get('costCentre') or {}
            data.append((
                voucher.get('id'),
                voucher.get('voucherNumber'),
                voucher.get('voucherDate'),
                voucher.get('status'),
                float(voucher.get('sumNet', 0) or 0),
                cost_center.get('id') if cost_center else None,
                cost_center.get('name') if cost_center else None,
                voucher.get('supplier', {}).get('name') if voucher.get('supplier') else None,
                voucher.get('create'),  # SevDesk uses 'create' not 'createTimestamp'
                voucher.get('update'),  # SevDesk uses 'update' not 'updateTimestamp'
                json.dumps(voucher),
                now
            ))
        
        cursor.executemany('''
            INSERT OR REPLACE INTO voucher_cache
            (id, voucher_number, voucher_date, status, amount, 
             cost_center_id, cost_center_name, supplier_name,
             create_timestamp, update_timestamp, voucher_data, cached_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', data)
        
        conn.commit()
        conn.close()
    
    def save_positions_to_cache_batch(self, positions_by_voucher: Dict[str, List[Dict]]):
        """Save multiple voucher positions to cache in a batch."""
        import json
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        now = datetime.now().isoformat()
        
        data = []
        for voucher_id, positions in positions_by_voucher.items():
            for position in positions:
                accounting_type = position.get('accountingType') or {}
                data.append((
                    position.get('id'),
                    voucher_id,
                    accounting_type.get('id') if accounting_type else None,
                    accounting_type.get('name') if accounting_type else None,
                    float(position.get('sumNet', 0) or 0),
                    float(position.get('taxRate', 0) or 0),
                    position.get('comment'),
                    json.dumps(position),
                    now
                ))
        
        cursor.executemany('''
            INSERT OR REPLACE INTO voucher_position_cache
            (id, voucher_id, accounting_type_id, accounting_type_name,
             sum_net, tax_rate, comment, position_data, cached_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', data)
        
        conn.commit()
        conn.close()
    
    def get_cached_vouchers(self, voucher_ids: Optional[List[str]] = None) -> List[Dict]:
        """Get cached vouchers. If voucher_ids provided, get only those."""
        import json
        
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        if voucher_ids:
            placeholders = ','.join(['?'] * len(voucher_ids))
            cursor.execute(f'SELECT * FROM voucher_cache WHERE id IN ({placeholders})', voucher_ids)
        else:
            cursor.execute('SELECT * FROM voucher_cache')
        
        rows = cursor.fetchall()
        conn.close()
        
        return [json.loads(row['voucher_data']) for row in rows]
    
    def get_cached_positions_batch(self, voucher_ids: List[str]) -> Dict[str, List[Dict]]:
        """Get cached positions for multiple vouchers."""
        import json
        
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        placeholders = ','.join(['?'] * len(voucher_ids))
        cursor.execute(f'''
            SELECT * FROM voucher_position_cache
            WHERE voucher_id IN ({placeholders})
        ''', voucher_ids)
        
        rows = cursor.fetchall()
        conn.close()
        
        # Group by voucher_id
        positions_by_voucher = {}
        for row in rows:
            voucher_id = row['voucher_id']
            if voucher_id not in positions_by_voucher:
                positions_by_voucher[voucher_id] = []
            positions_by_voucher[voucher_id].append(json.loads(row['position_data']))
        
        return positions_by_voucher
    
    def get_voucher_cache_stats(self) -> Dict:
        """Get statistics about the voucher cache."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('SELECT COUNT(*) as count FROM voucher_cache')
        voucher_count = cursor.fetchone()[0]
        
        cursor.execute('SELECT COUNT(*) as count FROM voucher_position_cache')
        position_count = cursor.fetchone()[0]
        
        cursor.execute('SELECT MAX(cached_at) as last_update FROM voucher_cache')
        last_update = cursor.fetchone()[0]
        
        conn.close()
        
        return {
            'voucher_count': voucher_count,
            'position_count': position_count,
            'last_update': last_update
        }
    
    def get_max_update_timestamp(self) -> Optional[str]:
        """Get the maximum update_timestamp from cached vouchers."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('SELECT MAX(update_timestamp) FROM voucher_cache')
        result = cursor.fetchone()[0]
        
        conn.close()
        return result
    
    def clear_voucher_cache(self):
        """Clear all voucher and position cache."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('DELETE FROM voucher_position_cache')
        cursor.execute('DELETE FROM voucher_cache')
        
        conn.commit()
        conn.close()
    
    def mark_vouchers_as_edited(self, voucher_ids: List[str]):
        """Mark vouchers as edited (need refresh from API)."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        placeholders = ','.join(['?'] * len(voucher_ids))
        cursor.execute(f'''
            UPDATE voucher_cache 
            SET edited = 1
            WHERE id IN ({placeholders})
        ''', voucher_ids)
        
        conn.commit()
        conn.close()
    
    def get_edited_voucher_ids(self) -> List[str]:
        """Get IDs of vouchers marked as edited."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('SELECT id FROM voucher_cache WHERE edited = 1')
        rows = cursor.fetchall()
        
        conn.close()
        return [row[0] for row in rows]
    
    def clear_edited_flags(self, voucher_ids: Optional[List[str]] = None):
        """Clear edited flags for specific vouchers or all vouchers."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        if voucher_ids:
            placeholders = ','.join(['?'] * len(voucher_ids))
            cursor.execute(f'''
                UPDATE voucher_cache 
                SET edited = 0
                WHERE id IN ({placeholders})
            ''', voucher_ids)
        else:
            cursor.execute('UPDATE voucher_cache SET edited = 0')
        
        conn.commit()
        conn.close()
    
    def mark_voucher_validation(self, voucher_id: str, is_valid: bool, reason: str = None):
        """Mark a voucher as valid or invalid with validation reason."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            UPDATE voucher_cache
            SET is_valid = ?,
                validation_reason = ?,
                last_validated_at = ?
            WHERE id = ?
        ''', (1 if is_valid else 0, reason, datetime.now().isoformat(), voucher_id))
        
        conn.commit()
        conn.close()
    
    def get_invalid_voucher_ids(self) -> List[str]:
        """Get IDs of vouchers that failed validation."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('SELECT id FROM voucher_cache WHERE is_valid = 0')
        rows = cursor.fetchall()
        
        conn.close()
        return [row[0] for row in rows]
    
    def get_vouchers_updated_since(self, since_timestamp: str) -> List[str]:
        """Get IDs of vouchers updated since given timestamp."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT id FROM voucher_cache 
            WHERE update_timestamp > ?
        ''', (since_timestamp,))
        rows = cursor.fetchall()
        
        conn.close()
        return [row[0] for row in rows]
    
    def get_invalid_vouchers(self) -> List[Dict[str, Any]]:
        """
        Get full details of vouchers that failed validation.
        
        Returns:
            List of invalid voucher dictionaries with all fields needed for reporting
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT 
                id,
                voucher_number,
                voucher_date,
                status,
                amount,
                supplier_name,
                cost_center_id,
                cost_center_name,
                validation_reason,
                last_validated_at
            FROM voucher_cache 
            WHERE is_valid = 0
            ORDER BY voucher_date DESC, voucher_number
        ''')
        rows = cursor.fetchall()
        
        conn.close()
        return [dict(row) for row in rows]
