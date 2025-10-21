"""SevDesk API client."""
import requests
import time
from typing import Dict, List, Optional
from datetime import datetime


class SevDeskClient:
    """Client for interacting with the SevDesk API."""
    
    def __init__(self, api_key: str, base_url: str = "https://my.sevdesk.de/api/v1"):
        """
        Initialize the SevDesk client.
        
        Args:
            api_key: SevDesk API key
            base_url: Base URL for the API
        """
        self.api_key = api_key
        self.base_url = base_url.rstrip('/')
        self.session = requests.Session()
        self.session.headers.update({
            'Authorization': api_key,
            'Content-Type': 'application/json'
        })
        self.rate_limit_delay = 0.1
        self.last_request_time = 0
    
    def __enter__(self):
        """Context manager entry."""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.session.close()
        return False
    
    def _rate_limit(self):
        """Simple rate limiting to avoid overwhelming the API."""
        elapsed = time.time() - self.last_request_time
        if elapsed < self.rate_limit_delay:
            time.sleep(self.rate_limit_delay - elapsed)
        self.last_request_time = time.time()
    
    def _request(self, method: str, endpoint: str, params: Optional[Dict] = None) -> Dict:
        """
        Make an API request.
        
        Args:
            method: HTTP method (GET, POST, etc.)
            endpoint: API endpoint (e.g., '/Voucher')
            params: Query parameters
        
        Returns:
            JSON response
        
        Raises:
            requests.HTTPError: If the request fails
        """
        self._rate_limit()
        url = f"{self.base_url}{endpoint}"
        response = self.session.request(method=method, url=url, params=params)
        response.raise_for_status()
        return response.json()
    
    def get_cost_centers(self) -> List[Dict]:
        """
        Fetch all cost centers (Kostenstellen).
        
        Returns:
            List of cost center objects
        """
        response = self._request('GET', '/CostCentre', params={'limit': 1000})
        return response.get('objects', [])
    
    def get_accounts(self) -> List[Dict]:
        """
        Fetch all check accounts from SevDesk.
        
        Returns:
            List of check account objects (bank accounts, cash, PayPal, etc.)
        """
        response = self._request('GET', '/CheckAccount', params={'limit': 1000})
        return response.get('objects', [])
    
    def get_vouchers(
        self,
        status: Optional[int] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        limit: Optional[int] = None
    ) -> List[Dict]:
        """
        Fetch vouchers (Belege) from SevDesk.
        
        Args:
            status: Filter by status (50=Draft, 100=Unpaid, 1000=Paid)
            date_from: Start date in YYYY-MM-DD format
            date_to: End date in YYYY-MM-DD format
            limit: Maximum number of vouchers to fetch
        
        Returns:
            List of voucher objects
        """
        params = {'limit': 100, 'offset': 0}
        
        if status is not None:
            params['status'] = status
        if date_from:
            params['startDate'] = date_from
        if date_to:
            params['endDate'] = date_to
        
        all_vouchers = []
        
        while True:
            response = self._request('GET', '/Voucher', params=params)
            vouchers = response.get('objects', [])
            
            if not vouchers:
                break
            
            all_vouchers.extend(vouchers)
            
            # Stop if we've reached the limit
            if limit and len(all_vouchers) >= limit:
                all_vouchers = all_vouchers[:limit]
                break
            
            # Stop if this was the last page
            if len(vouchers) < params['limit']:
                break
            
            params['offset'] += params['limit']
        
        return all_vouchers
    
    def get_voucher(self, voucher_id: str) -> Optional[Dict]:
        """
        Fetch a single voucher by ID.
        
        Args:
            voucher_id: ID of the voucher
        
        Returns:
            Voucher object or None if not found
        """
        try:
            response = self._request('GET', f'/Voucher/{voucher_id}')
            objects = response.get('objects', [])
            return objects[0] if objects else None
        except requests.HTTPError as e:
            if e.response.status_code == 404:
                return None
            raise
    
    def get_voucher_positions(self, voucher_id: str) -> List[Dict]:
        """
        Fetch positions (line items) for a voucher.
        
        Args:
            voucher_id: ID of the voucher
        
        Returns:
            List of voucher position objects
        """
        params = {
            'voucher[id]': voucher_id,
            'voucher[objectName]': 'Voucher',
            'limit': 100
        }
        response = self._request('GET', '/VoucherPos', params=params)
        return response.get('objects', [])
    
    def get_voucher_positions_batch(self, voucher_ids: List[str], show_progress: bool = False) -> Dict[str, List[Dict]]:
        """
        Fetch positions for multiple vouchers efficiently.
        
        This method makes individual API calls for each voucher but removes
        the rate limiting delay between calls (batching the requests together).
        This is faster than the old approach when you have many vouchers.
        
        Args:
            voucher_ids: List of voucher IDs
            show_progress: If True, show a progress bar
        
        Returns:
            Dictionary mapping voucher_id -> list of position objects
        """
        if not voucher_ids:
            return {}
        
        positions_by_voucher = {}
        
        # Temporarily disable rate limiting for batch operation
        original_delay = self.rate_limit_delay
        self.rate_limit_delay = 0.01  # Minimal delay (10ms instead of 100ms)
        
        try:
            if show_progress:
                from tqdm import tqdm
                iterator = tqdm(voucher_ids, desc="Fetching positions", unit="voucher")
            else:
                iterator = voucher_ids
            
            for voucher_id in iterator:
                positions_by_voucher[voucher_id] = self.get_voucher_positions(voucher_id)
        finally:
            # Restore original rate limiting
            self.rate_limit_delay = original_delay
        
        return positions_by_voucher
    
    def get_accounting_type(self, accounting_type_id: str) -> Dict:
        """
        Fetch details of an accounting type.
        
        Args:
            accounting_type_id: ID of the accounting type
        
        Returns:
            Accounting type object
        """
        response = self._request('GET', f'/AccountingType/{accounting_type_id}')
        objects = response.get('objects', [])
        return objects[0] if objects else {}
    
    def get_voucher_check_account_transactions(self, voucher_id: str) -> List[Dict]:
        """
        Fetch CheckAccountTransactions for a voucher to determine which account was used.
        
        Args:
            voucher_id: ID of the voucher
        
        Returns:
            List of CheckAccountTransaction objects containing account information
        """
        response = self._request('GET', '/CheckAccountTransaction', params={
            'voucher[id]': voucher_id,
            'voucher[objectName]': 'Voucher'
        })
        return response.get('objects', [])

