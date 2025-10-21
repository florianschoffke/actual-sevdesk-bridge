"""Actual Budget API client."""
from decimal import Decimal
from datetime import date
from typing import Dict, List, Optional
from actual import Actual
from actual.queries import (
    create_transaction,
    create_account,
    create_category as actual_create_category,
    get_accounts,
    get_payees,
    get_categories,
    get_or_create_category_group
)
import urllib3

# Disable SSL warnings when SSL verification is disabled
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)



class ActualBudgetClient:
    """Client for interacting with Actual Budget."""
    
    def __init__(
        self,
        base_url: str,
        password: str,
        file_id: str,
        verify_ssl: bool = True
    ):
        """
        Initialize the Actual Budget client.
        
        Args:
            base_url: Base URL of Actual Budget server
            password: Password for the budget file
            file_id: ID of the budget file
            verify_ssl: Whether to verify SSL certificates
        """
        self.base_url = base_url
        self.password = password
        self.file_id = file_id
        self.verify_ssl = verify_ssl
        self._actual = None
    
    def __enter__(self):
        """Context manager entry."""
        self._actual = Actual(
            base_url=self.base_url,
            password=self.password,
            file=self.file_id,
            cert=self.verify_ssl
        )
        # Enter the Actual context manager
        self._actual.__enter__()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - commit and upload changes."""
        if self._actual:
            # Commit changes to sync to server
            try:
                self._actual.commit()
            except Exception as e:
                print(f"Warning: Failed to commit changes: {e}")
            return self._actual.__exit__(exc_type, exc_val, exc_tb)
        return False
    
    def flush(self):
        """Flush pending changes to local database (doesn't sync to server yet)."""
        if self._actual and self._actual.session:
            self._actual.session.flush()
    
    def get_accounts(self) -> List[Dict]:
        """
        Get all accounts.
        
        Returns:
            List of account dictionaries
        """
        accounts = get_accounts(self._actual.session)
        return [
            {
                'id': str(acc.id),
                'name': acc.name,
                'offbudget': acc.offbudget,
                'closed': acc.closed
            }
            for acc in accounts
        ]
    
    def get_or_create_account(self, name: str, offbudget: bool = False) -> Dict:
        """
        Get an existing account by name or create it if it doesn't exist.
        
        Args:
            name: Account name
            offbudget: Whether this is an off-budget (tracking) account
        
        Returns:
            Account dictionary
        """
        accounts = self.get_accounts()
        for acc in accounts:
            if acc['name'] == name:
                return acc
        
        # Create the account if it doesn't exist
        return self.create_account(name, offbudget)
    
    def create_account(self, name: str, offbudget: bool = False) -> Dict:
        """
        Create a new account.
        
        Args:
            name: Account name
            offbudget: Whether this is an off-budget (tracking) account
        
        Returns:
            Created account dictionary
        """
        account = create_account(self._actual.session, name, off_budget=offbudget)
        self._actual.commit()
        return {
            'id': str(account.id),
            'name': account.name,
            'offbudget': account.offbudget,
            'closed': account.closed
        }
    
    def get_first_transaction_month_for_category(self, category_id: str) -> Optional[date]:
        """
        Get the first month that has transactions for a given category.
        
        Args:
            category_id: Category ID
        
        Returns:
            Date representing the first month with transactions, or None if no transactions
        """
        from actual.database import Transactions
        from sqlalchemy import select, func
        from datetime import datetime
        
        # Query for the earliest transaction date for this category
        # Note: Use category_id field, not the category relationship
        stmt = select(func.min(Transactions.date)).where(
            Transactions.category_id == category_id,
            Transactions.tombstone == 0
        )
        result = self._actual.session.execute(stmt).scalar()
        
        if result:
            # Convert YYYYMMDD integer to date (first day of that month)
            date_str = str(result)
            if len(date_str) == 8:
                year = int(date_str[:4])
                month = int(date_str[4:6])
                return date(year, month, 1)
        
        return None
    
    def enable_category_carryover_for_first_month(self, category_id: str) -> bool:
        """
        Enable carryover for a category starting from its first month with transactions.
        
        In Actual Budget, carryover must be enabled for each month. This function:
        1. Finds the first month with transactions
        2. Enables carryover from that month through the current month
        3. This allows past balances to roll forward to today
        
        Args:
            category_id: Category ID
        
        Returns:
            True if carryover was enabled for any month, False if no transactions found
        """
        from actual.database import ZeroBudgets
        from sqlalchemy import select, and_
        from datetime import datetime
        from dateutil.relativedelta import relativedelta
        
        # Get the first month with transactions
        first_month = self.get_first_transaction_month_for_category(category_id)
        
        if not first_month:
            # No transactions yet, nothing to do
            return False
        
        # Get current month and set carryover through end of next year
        # This ensures carryover is set well into the future
        current_month = date.today().replace(day=1)
        end_month = date(current_month.year + 1, 12, 1)  # End of next year
        
        # Enable carryover for all months from first transaction through end of next year
        month_iterator = first_month
        months_updated = 0
        
        while month_iterator <= end_month:
            month_str = month_iterator.strftime('%Y-%m')
            
            # Check if a budget entry exists for this category and month
            stmt = select(ZeroBudgets).where(
                and_(
                    ZeroBudgets.category_id == category_id,
                    ZeroBudgets.month == month_str
                )
            )
            budget_entry = self._actual.session.execute(stmt).scalar_one_or_none()
            
            if budget_entry:
                # Update existing budget entry to enable carryover
                if not budget_entry.carryover:
                    budget_entry.carryover = 1
                    months_updated += 1
            else:
                # Create a new budget entry with carryover enabled
                from uuid import uuid4
                new_budget = ZeroBudgets(
                    id=str(uuid4()),
                    month=month_str,
                    category_id=category_id,
                    amount=0,  # No budget amount, just carryover setting
                    carryover=1
                )
                self._actual.session.add(new_budget)
                months_updated += 1
            
            # Move to next month
            month_iterator = month_iterator + relativedelta(months=1)
        
        if months_updated > 0:
            self._actual.session.flush()
            return True
        
        return False
    
    def enable_carryover_for_all_categories(self) -> Dict[str, int]:
        """
        Enable carryover for all categories for their first month with transactions.
        
        Returns:
            Dictionary with statistics: {'processed': int, 'enabled': int, 'skipped': int}
        """
        categories = self.get_categories()
        processed = 0
        enabled = 0
        skipped = 0
        
        for category in categories:
            processed += 1
            if self.enable_category_carryover_for_first_month(category['id']):
                enabled += 1
            else:
                skipped += 1
        
        # Flush all changes
        self._actual.session.flush()
        
        return {
            'processed': processed,
            'enabled': enabled,
            'skipped': skipped
        }
    
    def check_and_extend_carryover(self, months_ahead: int = 12) -> Dict[str, int]:
        """
        Check if carryover is set far enough into the future and extend if needed.
        
        This is meant to be called automatically during sync operations to ensure
        carryover settings don't expire. Optimized to only check categories that
        need checking.
        
        Args:
            months_ahead: Minimum number of months ahead to ensure carryover is set (default: 12)
        
        Returns:
            Dictionary with statistics: {'checked': int, 'extended': int, 'already_ok': int}
        """
        from actual.database import ZeroBudgets, Transactions
        from sqlalchemy import select, func, and_
        from datetime import date
        from dateutil.relativedelta import relativedelta
        import logging
        
        logger = logging.getLogger(__name__)
        current_month = date.today().replace(day=1)
        target_month = current_month + relativedelta(months=months_ahead)
        target_month_str = target_month.strftime('%Y-%m')
        
        checked = 0
        extended = 0
        already_ok = 0
        
        # Optimization: Get all categories that have transactions
        stmt = select(Transactions.category_id).where(
            Transactions.category_id.isnot(None),
            Transactions.tombstone == 0
        ).distinct()
        categories_with_transactions = [row[0] for row in self._actual.session.execute(stmt).all()]
        
        logger.debug(f"Found {len(categories_with_transactions)} categories with transactions")
        
        for cat_id in categories_with_transactions:
            checked += 1
            
            # Check if carryover is set for the target month
            stmt = select(ZeroBudgets).where(
                and_(
                    ZeroBudgets.category_id == cat_id,
                    ZeroBudgets.month == target_month_str,
                    ZeroBudgets.carryover == 1
                )
            )
            has_future_carryover = self._actual.session.execute(stmt).scalar_one_or_none()
            
            if has_future_carryover:
                # Carryover already set for target month
                already_ok += 1
            else:
                # Need to extend carryover
                logger.debug(f"Extending carryover for category {cat_id}")
                self.enable_category_carryover_for_first_month(cat_id)
                extended += 1
        
        if extended > 0:
            self._actual.session.flush()
        
        return {
            'checked': checked,
            'extended': extended,
            'already_ok': already_ok
        }
    
    def get_payees(self) -> List[Dict]:
        """
        Get all payees.
        
        Returns:
            List of payee dictionaries
        """
        payees = get_payees(self._actual.session)
        return [
            {
                'id': str(p.id),
                'name': p.name
            }
            for p in payees
        ]
    
    def get_categories(self) -> List[Dict]:
        """
        Get all categories.
        
        Returns:
            List of category dictionaries
        """
        categories = get_categories(self._actual.session)
        result = []
        for cat in categories:
            result.append({
                'id': str(cat.id),
                'name': cat.name,
                'is_income': cat.is_income,
                'group_id': str(cat.cat_group) if cat.cat_group else None
            })
        return result
    
    def create_payee(self, name: str) -> Dict:
        """
        Create a payee.
        
        Args:
            name: Name of the payee
            
        Returns:
            Payee dictionary with id and name
        """
        # Check if payee already exists
        payees = get_payees(self._actual.session)
        for p in payees:
            if p.name == name:
                return {
                    'id': str(p.id),
                    'name': p.name
                }
        
        # Create new payee (payees are created automatically by Actual)
        # For now, return None and let the transaction create it
        return None
    
    def get_or_create_category_group(self, name: str) -> str:
        """
        Get or create a category group.
        
        Args:
            name: Name of the category group
            
        Returns:
            Category group name (for use with create_category)
        """
        group = get_or_create_category_group(self._actual.session, name)
        return group.name
    
    def create_category(self, name: str, group_name: str, is_income: bool = False, enable_carryover: bool = True) -> Dict:
        """
        Create a new category using the library's create_category function.
        
        Args:
            name: Category name
            group_name: Category group name (will be created if doesn't exist)
            is_income: Whether this is an income category
            enable_carryover: Whether to enable carryover for the category's first month with transactions
        
        Returns:
            Created category dictionary
        """
        # Use the library's create_category function which properly handles category creation
        category = actual_create_category(self._actual.session, name, group_name)
        
        # Set is_income if needed (library's create_category doesn't support this parameter)
        if is_income:
            category.is_income = 1
            self._actual.session.flush()
        
        # Enable carryover for the first month with transactions if requested
        if enable_carryover:
            self.enable_category_carryover_for_first_month(str(category.id))
        
        return {
            'id': str(category.id),
            'name': category.name,
            'is_income': bool(category.is_income),
            'group_id': str(category.cat_group) if category.cat_group else None
        }
    
    def create_transaction(
        self,
        account_id: str,
        date: date,
        amount: int,
        payee_id: Optional[str] = None,
        category_id: Optional[str] = None,
        notes: Optional[str] = None
    ) -> Dict:
        """
        Create a transaction.
        
        Args:
            account_id: Account ID
            date: Transaction date
            amount: Amount in cents (positive for expenses, negative for income)
            payee_id: Payee ID (optional)
            category_id: Category ID (optional)
            notes: Transaction notes (optional)
        
        Returns:
            Created transaction dictionary
        """
        # Convert cents to Decimal
        amount_decimal = Decimal(amount) / 100
        
        # If category_id is provided, fetch the actual Category object
        # The library expects a Categories object, not just a string ID
        category_obj = None
        if category_id:
            from actual.database import Categories
            category_obj = self._actual.session.get(Categories, category_id)
            if not category_obj:
                # Category doesn't exist, log a warning but continue
                print(f"Warning: Category {category_id} not found in database")
        
        # Create transaction
        txn = create_transaction(
            self._actual.session,
            date=date,
            account=account_id,
            payee=payee_id,
            notes=notes,
            category=category_obj,  # Pass the Category object, not the string ID
            amount=amount_decimal
        )
        
        # Commit changes
        self._actual.commit()
        
        return {
            'id': str(txn.id),
            'date': txn.date,
            'amount': amount,
            'account_id': account_id,
            'payee_id': payee_id,
            'category_id': category_id,
            'notes': notes
        }
    
    def update_transaction(
        self,
        transaction_id: str,
        date: Optional[date] = None,
        amount: Optional[int] = None,
        category_id: Optional[str] = None,
        notes: Optional[str] = None
    ) -> Dict:
        """
        Update an existing transaction.
        
        Args:
            transaction_id: Transaction ID to update
            date: New transaction date (optional)
            amount: New amount in cents (optional)
            category_id: New category ID (optional)
            notes: New transaction notes (optional)
        
        Returns:
            Updated transaction dictionary
        """
        from actual.database import Transactions, Categories
        from sqlalchemy import text
        
        # Build update query dynamically based on provided fields
        updates = []
        params = {'id': transaction_id}
        
        if date is not None:
            updates.append('date = :date')
            params['date'] = int(date.strftime('%Y%m%d'))
        
        if amount is not None:
            updates.append('amount = :amount')
            params['amount'] = int(amount)  # Store as integer (cents)
        
        if category_id is not None:
            # Verify category exists
            category_obj = self._actual.session.get(Categories, category_id)
            if category_obj:
                updates.append('category = :category')
                params['category'] = category_id
            else:
                print(f"Warning: Category {category_id} not found, setting to NULL")
                updates.append('category = NULL')
        
        if notes is not None:
            updates.append('notes = :notes')
            params['notes'] = notes
        
        if not updates:
            # Nothing to update
            return {'id': transaction_id}
        
        # Execute update
        update_sql = f"UPDATE transactions SET {', '.join(updates)} WHERE id = :id AND tombstone = 0"
        self._actual.session.execute(text(update_sql), params)
        self._actual.commit()
        
        return {
            'id': transaction_id,
            'date': params.get('date'),
            'amount': params.get('amount'),
            'category_id': category_id,
            'notes': params.get('notes')
        }
    
    def delete_transaction(self, transaction_id: str) -> bool:
        """
        Delete a transaction by setting its tombstone flag.
        
        Args:
            transaction_id: Transaction ID to delete
        
        Returns:
            True if deleted, False if not found
        """
        from sqlalchemy import text
        
        # Check if transaction exists
        result = self._actual.session.execute(
            text('SELECT id FROM transactions WHERE id = :id AND tombstone = 0'),
            {'id': transaction_id}
        )
        
        if not result.fetchone():
            return False
        
        # Set tombstone flag (Actual Budget's soft delete)
        self._actual.session.execute(
            text('UPDATE transactions SET tombstone = 1 WHERE id = :id'),
            {'id': transaction_id}
        )
        
        self._actual.commit()
        return True


    def create_transactions_batch(
        self,
        transactions: List[Dict]
    ) -> List[Dict]:
        """
        Create multiple transactions in a single batch operation.
        
        This is much faster than creating transactions one-by-one.
        
        Args:
            transactions: List of transaction dictionaries, each containing:
                - account_id: Account ID (required)
                - date: Transaction date (required)
                - amount: Amount in cents (required)
                - payee_id: Payee ID (optional)
                - category_id: Category ID (optional)
                - notes: Transaction notes (optional)
        
        Returns:
            List of created transaction dictionaries with IDs
        """
        from actual.database import Transactions, Categories
        from uuid import uuid4
        
        if not transactions:
            return []
        
        # Prepare transaction data for bulk insert
        bulk_data = []
        result_transactions = []
        
        for txn_data in transactions:
            # Generate UUID for transaction
            txn_id = str(uuid4())
            
            # Convert date to Actual Budget format (YYYYMMDD as integer)
            date_int = int(txn_data['date'].strftime('%Y%m%d'))
            
            # Amount is already in cents
            amount_cents = txn_data['amount']
            
            # Validate category if provided
            category_id = txn_data.get('category_id')
            if category_id:
                category_obj = self._actual.session.get(Categories, category_id)
                if not category_obj:
                    print(f"Warning: Category {category_id} not found, using NULL")
                    category_id = None
            
            # Build transaction record
            record = {
                'id': txn_id,
                'acct': txn_data['account_id'],
                'date': date_int,
                'amount': amount_cents,
                'payee': txn_data.get('payee_id'),
                'category': category_id,
                'notes': txn_data.get('notes', ''),
                'cleared': 0,
                'tombstone': 0,
                'starting_balance_flag': 0,
                'transferred_id': None,
                'sort_order': None
            }
            
            bulk_data.append(record)
            
            # Build result dictionary
            result_transactions.append({
                'id': txn_id,
                'account_id': txn_data['account_id'],
                'date': txn_data['date'],
                'amount': amount_cents,
                'payee_id': txn_data.get('payee_id'),
                'category_id': category_id,
                'notes': txn_data.get('notes', '')
            })
        
        # Bulk insert all transactions
        self._actual.session.bulk_insert_mappings(Transactions, bulk_data)
        
        # Flush to local database first
        self._actual.session.flush()
        
        # Commit and upload to server
        print(f"📤 Committing {len(bulk_data)} transactions to local database...")
        self._actual.commit()
        print(f"📤 Uploading {len(bulk_data)} transactions to server...")
        self._actual.upload_budget()
        print(f"✅ Upload complete!")
        
        return result_transactions
    
    def update_transactions_batch(
        self,
        transactions: List[Dict]
    ) -> List[Dict]:
        """
        Update multiple transactions in a single batch operation.
        
        Args:
            transactions: List of transaction dictionaries, each containing:
                - id: Transaction ID to update (required)
                - date: New transaction date (optional)
                - amount: New amount in cents (optional)
                - category_id: New category ID (optional)
                - notes: New transaction notes (optional)
        
        Returns:
            List of updated transaction dictionaries
        """
        from actual.database import Transactions, Categories
        
        if not transactions:
            return []
        
        # Prepare update data
        bulk_updates = []
        result_transactions = []
        
        for txn_data in transactions:
            txn_id = txn_data['id']
            
            # Build update record (only include changed fields)
            update_record = {'id': txn_id}
            
            if 'date' in txn_data and txn_data['date'] is not None:
                update_record['date'] = int(txn_data['date'].strftime('%Y%m%d'))
            
            if 'amount' in txn_data and txn_data['amount'] is not None:
                update_record['amount'] = int(txn_data['amount'])
            
            if 'category_id' in txn_data:
                category_id = txn_data['category_id']
                if category_id:
                    # Verify category exists
                    category_obj = self._actual.session.get(Categories, category_id)
                    if category_obj:
                        update_record['category'] = category_id
                    else:
                        print(f"Warning: Category {category_id} not found, setting to NULL")
                        update_record['category'] = None
                else:
                    update_record['category'] = None
            
            if 'notes' in txn_data:
                update_record['notes'] = txn_data['notes']
            
            bulk_updates.append(update_record)
            result_transactions.append({'id': txn_id, **txn_data})
        
        # Bulk update all transactions
        if bulk_updates:
            self._actual.session.bulk_update_mappings(Transactions, bulk_updates)
            self._actual.session.flush()
            print(f"📤 Committing {len(bulk_updates)} transaction updates to local database...")
            self._actual.commit()
            print(f"📤 Uploading {len(bulk_updates)} transaction updates to server...")
            self._actual.upload_budget()
            print(f"✅ Upload complete!")
        
        return result_transactions
    
    def import_transactions(
        self,
        account_id: str,
        transactions: List[Dict]
    ) -> Dict:
        """
        Import transactions with automatic deduplication and reconciliation.
        
        This method mimics the Actual Budget importTransactions API behavior:
        - Uses imported_id to avoid duplicates
        - Reconciles similar transactions by amount, date, and payee
        - Automatically runs rules on imported transactions
        
        Args:
            account_id: Account ID to import transactions into
            transactions: List of transaction dictionaries, each containing:
                - date: Transaction date (required)
                - amount: Amount in cents (required)
                - payee_name: Payee name (optional, will auto-create)
                - payee_id: Payee ID (optional, overrides payee_name)
                - category_id: Category ID (optional)
                - notes: Transaction notes (optional)
                - imported_id: Unique ID from source system (optional but recommended)
                - imported_payee: Original payee description (optional)
                - cleared: Whether transaction is cleared (optional, default False)
        
        Returns:
            Dictionary with:
                - added: List of IDs of newly added transactions
                - updated: List of IDs of transactions that were updated
                - skipped: List of imported_ids that were skipped as duplicates
        """
        from actual.database import Transactions, Payees
        from actual.queries import get_or_create_payee, set_transaction_payee
        from sqlalchemy import select, and_, or_
        import uuid
        from datetime import timedelta
        
        if not transactions:
            return {'added': [], 'updated': [], 'skipped': []}
        
        added = []
        updated = []
        skipped = []
        
        # Get existing transactions with imported_id for quick duplicate check
        existing_imported_ids = set()
        if any('imported_id' in t for t in transactions):
            imported_ids = [t['imported_id'] for t in transactions if t.get('imported_id')]
            if imported_ids:
                stmt = select(Transactions.financial_id).where(
                    and_(
                        Transactions.acct == account_id,
                        Transactions.financial_id.in_(imported_ids),
                        Transactions.tombstone == 0
                    )
                )
                result = self._actual.session.execute(stmt)
                existing_imported_ids = {row[0] for row in result if row[0]}
        
        # Process each transaction
        for txn_data in transactions:
            imported_id = txn_data.get('imported_id')
            
            # Skip if already imported (by imported_id)
            if imported_id and imported_id in existing_imported_ids:
                skipped.append(imported_id)
                continue
            
            # Convert date to integer format
            txn_date = txn_data['date']
            date_int = int(txn_date.strftime('%Y%m%d'))
            amount_cents = txn_data['amount']
            
            # Check for similar transactions (amount match within 3 days)
            date_window_start = int((txn_date - timedelta(days=3)).strftime('%Y%m%d'))
            date_window_end = int((txn_date + timedelta(days=3)).strftime('%Y%m%d'))
            
            stmt = select(Transactions).where(
                and_(
                    Transactions.acct == account_id,
                    Transactions.amount == amount_cents,
                    Transactions.date >= date_window_start,
                    Transactions.date <= date_window_end,
                    Transactions.tombstone == 0
                )
            )
            similar_txns = list(self._actual.session.execute(stmt).scalars())
            
            # If we find a similar transaction without imported_id, update it
            if similar_txns:
                existing_txn = similar_txns[0]
                
                # Update the existing transaction
                if imported_id:
                    existing_txn.financial_id = imported_id
                if txn_data.get('imported_payee'):
                    existing_txn.imported_description = txn_data['imported_payee']
                if 'notes' in txn_data:  # Update notes even if empty
                    existing_txn.notes = txn_data['notes']
                if 'cleared' in txn_data:
                    existing_txn.cleared = int(txn_data['cleared'])
                
                # Update payee if provided
                if 'payee_id' in txn_data or 'payee_name' in txn_data:
                    payee_id = txn_data.get('payee_id')
                    if not payee_id and txn_data.get('payee_name'):
                        payee = get_or_create_payee(self._actual.session, txn_data['payee_name'])
                        payee_id = str(payee.id)
                    if payee_id:
                        set_transaction_payee(self._actual.session, existing_txn, payee_id)
                
                # Update category if provided
                if 'category_id' in txn_data:
                    existing_txn.category_id = txn_data['category_id']
                
                updated.append(str(existing_txn.id))
                
                if imported_id:
                    existing_imported_ids.add(imported_id)
            else:
                # Create new transaction
                txn_id = str(uuid.uuid4())
                
                # Handle payee
                payee_id = txn_data.get('payee_id')
                if not payee_id and txn_data.get('payee_name'):
                    payee = get_or_create_payee(self._actual.session, txn_data['payee_name'])
                    payee_id = str(payee.id)
                
                # Create transaction record
                new_txn = Transactions(
                    id=txn_id,
                    acct=account_id,
                    date=date_int,
                    amount=amount_cents,
                    category_id=txn_data.get('category_id'),  # Use category_id, not category
                    notes=txn_data.get('notes', ''),
                    cleared=int(txn_data.get('cleared', False)),
                    financial_id=imported_id,
                    imported_description=txn_data.get('imported_payee'),
                    tombstone=0,
                    starting_balance_flag=0,
                    reconciled=0,
                    sort_order=date_int  # Use date_int for sort order
                )
                
                self._actual.session.add(new_txn)
                
                # Set payee (this handles payee logic)
                if payee_id:
                    set_transaction_payee(self._actual.session, new_txn, payee_id)
                
                added.append(txn_id)
                
                if imported_id:
                    existing_imported_ids.add(imported_id)
        
        # Flush changes to database
        self._actual.session.flush()
        
        # Run rules on all new/updated transactions
        if added or updated:
            print(f"📝 Running rules on {len(added) + len(updated)} transactions...")
            from actual.queries import get_ruleset
            
            # Get the transactions we just added/updated
            all_ids = added + updated
            stmt = select(Transactions).where(
                and_(
                    Transactions.id.in_(all_ids),
                    Transactions.tombstone == 0
                )
            )
            imported_txns = list(self._actual.session.execute(stmt).scalars())
            
            # Run rules
            ruleset = get_ruleset(self._actual.session)
            ruleset.run(imported_txns)
        
        # Commit all changes
        print(f"📤 Importing {len(added)} new, updating {len(updated)}, skipping {len(skipped)} transactions...")
        self._actual.commit()
        
        return {
            'added': added,
            'updated': updated,
            'skipped': skipped
        }

