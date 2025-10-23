"""Invoice validation logic for ensuring data quality."""
from typing import Dict, List
from dataclasses import dataclass


@dataclass
class InvoiceValidationResult:
    """Result of invoice validation."""
    is_valid: bool
    invoice_id: str
    invoice_date: str
    amount: float
    reason: str = ""
    invoice_number: str = ""


class InvoiceValidator:
    """Validates invoices before syncing to Actual Budget."""
    
    def __init__(
        self,
        category_mappings: Dict[str, str]
    ):
        """
        Initialize validator.
        
        Args:
            category_mappings: Dict of sevdesk_category_id -> actual_category_id
        """
        self.category_mappings = category_mappings
        self.validation_errors: List[InvoiceValidationResult] = []
    
    def validate_invoice(
        self,
        invoice: Dict,
        positions: List[Dict]
    ) -> InvoiceValidationResult:
        """
        Validate an invoice and its positions.
        
        Invoices must:
        1. Have at least one position
        2. Have a cost center assigned
        3. The cost center must be mapped to an Actual Budget category
        
        Args:
            invoice: Invoice data from SevDesk
            positions: List of invoice positions
            
        Returns:
            InvoiceValidationResult with validation outcome
        """
        invoice_id = str(invoice.get('id', ''))
        invoice_date = invoice.get('invoiceDate', '')
        invoice_number = invoice.get('invoiceNumber', '')
        amount = float(invoice.get('sumGross', 0))
        
        # Check if invoice has positions
        if not positions:
            result = InvoiceValidationResult(
                is_valid=False,
                invoice_id=invoice_id,
                invoice_date=invoice_date,
                amount=amount,
                invoice_number=invoice_number,
                reason="No invoice positions found"
            )
            self.validation_errors.append(result)
            return result
        
        # Check if invoice has a cost center
        # Invoices may have costCentre at the invoice level or at position level
        invoice_cost_centre = invoice.get('costCentre')
        
        # Collect all unique cost centers from positions
        position_cost_centres = set()
        for pos in positions:
            cost_centre = pos.get('costCentre')
            if cost_centre and cost_centre.get('id'):
                position_cost_centres.add(cost_centre.get('id'))
        
        # Determine the cost center to use
        cost_centre_id = None
        
        if invoice_cost_centre and invoice_cost_centre.get('id'):
            # Use invoice-level cost center
            cost_centre_id = invoice_cost_centre.get('id')
        elif len(position_cost_centres) == 1:
            # All positions have the same cost center
            cost_centre_id = list(position_cost_centres)[0]
        elif len(position_cost_centres) > 1:
            # Multiple different cost centers - invalid
            result = InvoiceValidationResult(
                is_valid=False,
                invoice_id=invoice_id,
                invoice_date=invoice_date,
                amount=amount,
                invoice_number=invoice_number,
                reason=f"Invoice has multiple cost centers across positions ({len(position_cost_centres)} different)"
            )
            self.validation_errors.append(result)
            return result
        
        # No cost center found
        if not cost_centre_id:
            result = InvoiceValidationResult(
                is_valid=False,
                invoice_id=invoice_id,
                invoice_date=invoice_date,
                amount=amount,
                invoice_number=invoice_number,
                reason="Invoice has no cost center assigned"
            )
            self.validation_errors.append(result)
            return result
        
        # Check if cost center is mapped to a category
        if cost_centre_id not in self.category_mappings:
            result = InvoiceValidationResult(
                is_valid=False,
                invoice_id=invoice_id,
                invoice_date=invoice_date,
                amount=amount,
                invoice_number=invoice_number,
                reason=f"Cost center {cost_centre_id} is not mapped to a category"
            )
            self.validation_errors.append(result)
            return result
        
        # Valid invoice
        return InvoiceValidationResult(
            is_valid=True,
            invoice_id=invoice_id,
            invoice_date=invoice_date,
            amount=amount,
            invoice_number=invoice_number
        )
    
    def get_validation_errors(self) -> List[InvoiceValidationResult]:
        """Get list of validation errors."""
        return self.validation_errors
    
    def clear_errors(self):
        """Clear validation errors."""
        self.validation_errors = []
