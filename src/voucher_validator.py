"""Voucher validation logic for ensuring data quality."""
from typing import Dict, List, Tuple
from dataclasses import dataclass
from pathlib import Path
from datetime import datetime


@dataclass
class ValidationResult:
    """Result of voucher validation."""
    is_valid: bool
    voucher_id: str
    voucher_date: str
    amount: float
    reason: str = ""
    voucher_type: str = ""  # 'regular', 'geldtransit', or 'unknown'
    voucher_number: str = ""  # Voucher number for easier identification
    

class VoucherValidator:
    """Validates vouchers before syncing to Actual Budget."""
    
    def __init__(
        self,
        account_mappings: Dict[str, str],
        category_mappings: Dict[str, str],
        geldtransit_type_ids: List[str] = None,
        no_cost_center_type_ids: List[str] = None
    ):
        """
        Initialize validator.
        
        Args:
            account_mappings: Dict of sevdesk_account_id -> actual_account_id
            category_mappings: Dict of sevdesk_category_id -> actual_category_id
            geldtransit_type_ids: List of accounting type IDs for Geldtransit (default: ['40', '81'])
            no_cost_center_type_ids: List of accounting type IDs that don't need cost centers (default: ['39'])
        """
        self.account_mappings = account_mappings
        self.category_mappings = category_mappings
        self.geldtransit_type_ids = geldtransit_type_ids or ['40', '81']
        self.no_cost_center_type_ids = no_cost_center_type_ids or ['39']  # Durchlaufende Posten
        self.validation_errors: List[ValidationResult] = []
    
    def validate_voucher(
        self,
        voucher: Dict,
        positions: List[Dict],
        voucher_number: str = ""
    ) -> ValidationResult:
        """
        Validate a voucher and its positions.
        
        Args:
            voucher: Voucher data from SevDesk
            positions: List of voucher positions
            voucher_number: Voucher number for identification
            
        Returns:
            ValidationResult with validation outcome
        """
        voucher_id = str(voucher.get('id', ''))
        voucher_date = voucher.get('voucherDate', '')
        amount = float(voucher.get('sumGross', 0))
        
        # Check if voucher has positions
        if not positions:
            result = ValidationResult(
                is_valid=False,
                voucher_id=voucher_id,
                voucher_date=voucher_date,
                amount=amount,
                reason="No voucher positions found",
                voucher_number=voucher_number
            )
            self.validation_errors.append(result)
            return result
        
        # Check if this is a Geldtransit voucher
        has_geldtransit = any(
            pos.get('accountingType', {}).get('id') in self.geldtransit_type_ids
            for pos in positions
        )
        
        # Check if this has an accounting type that doesn't need a cost center
        has_no_cc_type = any(
            pos.get('accountingType', {}).get('id') in self.no_cost_center_type_ids
            for pos in positions
        )
        
        if has_geldtransit:
            return self._validate_geldtransit(voucher, positions, voucher_number)
        elif has_no_cc_type:
            # Vouchers with "Durchlaufende Posten" or similar don't need cost centers
            return ValidationResult(
                is_valid=True,
                voucher_id=voucher_id,
                voucher_date=voucher_date,
                amount=amount,
                voucher_type='no_cost_center_required',
                voucher_number=voucher_number
            )
        else:
            return self._validate_regular_voucher(voucher, positions, voucher_number)
    
    def _validate_geldtransit(
        self,
        voucher: Dict,
        positions: List[Dict],
        voucher_number: str = ""
    ) -> ValidationResult:
        """Validate a Geldtransit (money transfer) voucher."""
        voucher_id = str(voucher.get('id', ''))
        voucher_date = voucher.get('voucherDate', '')
        amount = float(voucher.get('sumGross', 0))
        
        # Geldtransit should NOT have a cost center
        cost_centre = voucher.get('costCentre')
        if cost_centre and cost_centre.get('id'):
            result = ValidationResult(
                is_valid=False,
                voucher_id=voucher_id,
                voucher_date=voucher_date,
                amount=amount,
                voucher_type='geldtransit',
                reason="Geldtransit voucher has cost center (should be None)",
                voucher_number=voucher_number
            )
            self.validation_errors.append(result)
            return result
        
        # Geldtransit can have 1 or 2 positions (1 position is common for single-sided bookings)
        # Only validate if there are 0 or more than 2 positions
        if len(positions) == 0 or len(positions) > 2:
            result = ValidationResult(
                is_valid=False,
                voucher_id=voucher_id,
                voucher_date=voucher_date,
                amount=amount,
                voucher_type='geldtransit',
                reason=f"Geldtransit has {len(positions)} positions (expected 1 or 2)",
                voucher_number=voucher_number
            )
            self.validation_errors.append(result)
            return result
        
        # Valid Geldtransit
        return ValidationResult(
            is_valid=True,
            voucher_id=voucher_id,
            voucher_date=voucher_date,
            amount=amount,
            voucher_type='geldtransit',
            voucher_number=voucher_number
        )
    
    def _validate_regular_voucher(
        self,
        voucher: Dict,
        positions: List[Dict],
        voucher_number: str = ""
    ) -> ValidationResult:
        """Validate a regular voucher (expense/income)."""
        voucher_id = str(voucher.get('id', ''))
        voucher_date = voucher.get('voucherDate', '')
        amount = float(voucher.get('sumGross', 0))
        
        # Regular voucher MUST have a cost center
        cost_centre = voucher.get('costCentre')
        if not cost_centre or not cost_centre.get('id'):
            result = ValidationResult(
                is_valid=False,
                voucher_id=voucher_id,
                voucher_date=voucher_date,
                amount=amount,
                voucher_type='regular',
                reason="Regular voucher missing cost center",
                voucher_number=voucher_number
            )
            self.validation_errors.append(result)
            return result
        
        # Cost center must be mapped to Actual Budget category
        cost_centre_id = str(cost_centre.get('id'))
        if cost_centre_id not in self.category_mappings:
            result = ValidationResult(
                is_valid=False,
                voucher_id=voucher_id,
                voucher_date=voucher_date,
                amount=amount,
                voucher_type='regular',
                reason=f"Cost center {cost_centre_id} not mapped to Actual Budget category",
                voucher_number=voucher_number
            )
            self.validation_errors.append(result)
            return result
        
        # Valid regular voucher
        return ValidationResult(
            is_valid=True,
            voucher_id=voucher_id,
            voucher_date=voucher_date,
            amount=amount,
            voucher_type='regular',
            voucher_number=voucher_number
        )
    
    def get_validation_errors(self) -> List[ValidationResult]:
        """Get list of all validation errors."""
        return self.validation_errors
    
    def print_validation_summary(self, logger):
        """Print summary of validation errors."""
        if not self.validation_errors:
            logger.info("✅ All vouchers passed validation")
            return
        
        logger.warning(f"⚠️  {len(self.validation_errors)} vouchers failed validation:")
        logger.warning("")
        logger.warning(f"{'ID':<12} {'Date':<12} {'Amount':>10} {'Type':<12} {'Reason'}")
        logger.warning("-" * 80)
        
        for error in self.validation_errors:
            date_str = error.voucher_date[:10] if error.voucher_date else 'N/A'
            logger.warning(
                f"{error.voucher_id:<12} {date_str:<12} "
                f"€{error.amount:>9.2f} {error.voucher_type:<12} {error.reason}"
            )
        logger.warning("")
    
    def export_validation_errors_to_file(self, output_file: str = "invalid_vouchers.md") -> None:
        """
        Export validation errors to a markdown file with table format.
        File is overwritten on each run.
        
        Args:
            output_file: Path to output file (default: invalid_vouchers.md)
        """
        output_path = Path(output_file)
        
        with output_path.open('w', encoding='utf-8') as f:
            # Write header
            f.write("# Invalid Vouchers Report\n\n")
            f.write(f"**Generated**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
            
            if not self.validation_errors:
                f.write("✅ **All vouchers passed validation**\n\n")
                f.write("No invalid vouchers found during this sync.\n")
                return
            
            # Write summary
            f.write(f"**Total Invalid Vouchers**: {len(self.validation_errors)}\n\n")
            
            # Group errors by type
            errors_by_type = {}
            for error in self.validation_errors:
                error_type = error.voucher_type or 'unknown'
                if error_type not in errors_by_type:
                    errors_by_type[error_type] = []
                errors_by_type[error_type].append(error)
            
            # Write summary by type
            f.write("## Summary by Type\n\n")
            for error_type, errors in sorted(errors_by_type.items()):
                f.write(f"- **{error_type.capitalize()}**: {len(errors)} voucher(s)\n")
            f.write("\n")
            
            # Write detailed table
            f.write("## Detailed Invalid Vouchers\n\n")
            f.write("| Voucher # | Voucher ID | Date | Amount (€) | Type | Reason |\n")
            f.write("|-----------|------------|------|------------|------|--------|\n")
            
            # Sort by date (most recent first)
            sorted_errors = sorted(
                self.validation_errors,
                key=lambda x: x.voucher_date,
                reverse=True
            )
            
            for error in sorted_errors:
                date_str = error.voucher_date[:10] if error.voucher_date else 'N/A'
                voucher_num = error.voucher_number or 'N/A'
                voucher_type = error.voucher_type or 'unknown'
                
                f.write(
                    f"| {voucher_num} | {error.voucher_id} | {date_str} | "
                    f"{error.amount:.2f} | {voucher_type} | {error.reason} |\n"
                )
            
            f.write("\n")
            
            # Write explanations section
            f.write("## Common Validation Errors Explained\n\n")
            f.write("### Regular Voucher Issues\n\n")
            f.write("- **Missing cost center**: Regular expense/income vouchers must have a cost center assigned in SevDesk\n")
            f.write("- **Cost center not mapped**: The cost center exists but hasn't been synced to Actual Budget yet\n\n")
            f.write("### Geldtransit (Transfer) Issues\n\n")
            f.write("- **Has cost center**: Transfer vouchers should NOT have a cost center (leave it empty in SevDesk)\n")
            f.write("- **Wrong number of positions**: Transfers must have 1 or 2 positions (0 or more than 2 is invalid)\n\n")
            f.write("### General Issues\n\n")
            f.write("- **No voucher positions**: The voucher has no line items/positions in SevDesk\n\n")
            f.write("## How to Fix\n\n")
            f.write("1. Open SevDesk and navigate to the voucher using the Voucher ID\n")
            f.write("2. Review the reason for validation failure\n")
            f.write("3. Make the necessary corrections:\n")
            f.write("   - Add/remove cost center as needed\n")
            f.write("   - Ensure transfers have 1 or 2 positions\n")
            f.write("   - Verify all required fields are filled\n")
            f.write("4. Run the sync again\n\n")
            f.write("---\n")
            f.write("*This file is automatically generated and overwritten on each sync run.*\n")
