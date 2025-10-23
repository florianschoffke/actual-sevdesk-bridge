"""Email notifier for sending validation failure reports."""

import csv
import os
import smtplib
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from io import StringIO
from pathlib import Path
from typing import List, Dict, Any
import logging

logger = logging.getLogger(__name__)


class EmailNotifier:
    """Send email notifications with CSV attachments for validation failures."""
    
    def __init__(
        self,
        smtp_host: str,
        smtp_port: int,
        smtp_username: str,
        smtp_password: str,
        from_address: str,
        to_address: str,
        use_tls: bool = True,
        enabled: bool = True
    ):
        """
        Initialize email notifier.
        
        Args:
            smtp_host: SMTP server hostname
            smtp_port: SMTP server port
            smtp_username: SMTP username
            smtp_password: SMTP password
            from_address: Sender email address
            to_address: Recipient email address
            use_tls: Whether to use TLS encryption
            enabled: Whether email notifications are enabled
        """
        self.smtp_host = smtp_host
        self.smtp_port = smtp_port
        self.smtp_username = smtp_username
        self.smtp_password = smtp_password
        self.from_address = from_address
        self.to_address = to_address
        self.use_tls = use_tls
        self.enabled = enabled
    
    def create_csv_content(self, invalid_items: List[Dict[str, Any]], report_type: str = 'voucher') -> str:
        """
        Create CSV content from invalid items.
        
        Args:
            invalid_items: List of invalid item dictionaries
            report_type: Type of report - 'voucher' or 'invoice'
            
        Returns:
            CSV content as string
        """
        output = StringIO()
        writer = csv.writer(output)
        
        is_invoice = report_type == 'invoice'
        
        # Write header based on type
        if is_invoice:
            writer.writerow([
                'Invoice Number',
                'Invoice Date',
                'Status',
                'Amount (EUR)',
                'Contact',
                'Cost Center ID',
                'Cost Center Name',
                'Validation Reason',
                'Last Validated'
            ])
        else:
            writer.writerow([
                'Voucher Number',
                'Voucher Date',
                'Status',
                'Amount (EUR)',
                'Supplier',
                'Cost Center ID',
                'Cost Center Name',
                'Validation Reason',
                'Last Validated'
            ])
        
        # Write item data
        for item in invalid_items:
            if is_invoice:
                writer.writerow([
                    item.get('invoice_number', ''),
                    item.get('invoice_date', ''),
                    item.get('status', ''),
                    item.get('amount', ''),
                    item.get('contact_name', ''),
                    item.get('cost_center_id', ''),
                    item.get('cost_center_name', ''),
                    item.get('validation_reason', ''),
                    item.get('last_validated_at', '')
                ])
            else:
                writer.writerow([
                    item.get('voucher_number', ''),
                    item.get('voucher_date', ''),
                    item.get('status', ''),
                    item.get('amount', ''),
                    item.get('supplier_name', ''),
                    item.get('cost_center_id', ''),
                    item.get('cost_center_name', ''),
                    item.get('validation_reason', ''),
                    item.get('last_validated_at', '')
                ])
        
        return output.getvalue()
    
    def send_validation_report(self, invalid_items: List[Dict[str, Any]], report_type: str = 'voucher') -> bool:
        """
        Send email with invalid items CSV attachment.
        
        Args:
            invalid_items: List of invalid item dictionaries (vouchers or invoices)
            report_type: Type of report - 'voucher' or 'invoice'
            
        Returns:
            True if email sent successfully, False otherwise
        """
        if not self.enabled:
            logger.info("Email notifications disabled, skipping")
            return False
        
        if not invalid_items:
            logger.info(f"No invalid {report_type}s to report")
            return True
        
        try:
            # Determine item type and labels
            is_invoice = report_type == 'invoice'
            item_type = 'Invoice' if is_invoice else 'Voucher'
            item_type_plural = 'Invoices' if is_invoice else 'Vouchers'
            
            # Create message
            msg = MIMEMultipart()
            msg['From'] = self.from_address
            msg['To'] = self.to_address
            msg['Subject'] = f'{item_type} Validation Failed - {len(invalid_items)} Invalid {item_type_plural}'
            
            # Create table preview (first 10 items)
            preview_items = invalid_items[:10]
            table_lines = []
            table_lines.append("")
            table_lines.append(f"Invalid {item_type_plural}:")
            table_lines.append("-" * 100)
            
            for v in preview_items:
                item_id = v.get('id', '')
                item_num = v.get('invoice_number' if is_invoice else 'voucher_number', 'N/A')
                date = v.get('invoice_date' if is_invoice else 'voucher_date', 'N/A')
                amount = v.get('amount', 0)
                
                if is_invoice:
                    contact = v.get('contact_name', 'N/A') or 'N/A'
                    contact_label = 'Contact'
                else:
                    contact = v.get('supplier_name', 'N/A') or 'N/A'
                    contact_label = 'Supplier'
                
                reason = v.get('validation_reason', 'N/A')
                
                # Format with proper alignment
                table_lines.append(f"  {item_type}:  {item_num}")
                table_lines.append(f"  ID:       {item_id}")
                table_lines.append(f"  Link:     https://my.sevdesk.de/ex/detail/id/{item_id}")
                table_lines.append(f"  Date:     {date}")
                table_lines.append(f"  Amount:   €{amount:,.2f}")
                table_lines.append(f"  {contact_label}: {contact}")
                table_lines.append(f"  Reason:   {reason}")
                table_lines.append("-" * 100)
            
            if len(invalid_items) > 10:
                table_lines.append(f"\n... and {len(invalid_items) - 10} more {report_type}(s).")
                table_lines.append("See attached CSV for complete list.")
            
            table_preview = "\n".join(table_lines)
            
            # Email body based on type
            if is_invoice:
                common_issues = """Common validation issues:
- Invoices missing cost center assignment
- Invoices with multiple cost centers
- Cost centers not mapped to Actual Budget categories

Note: Stornorechnung (cancellation invoices) and cancelled invoices (paidAmount = 0) are automatically excluded and not errors."""
            else:
                common_issues = """Common validation issues:
- Regular vouchers missing cost center assignment
- Geldtransit vouchers incorrectly assigned cost centers
- Other accounting type mismatches"""
            
            # Email body
            body = f"""
{item_type} validation completed with failures.

Summary:
- Total invalid {report_type}s: {len(invalid_items)}
- Report generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

{table_preview}

{common_issues}

Please review the attached CSV file for complete details on which {report_type}s need correction.

The system will automatically re-validate these {report_type}s on the next sync once corrected.
"""
            msg.attach(MIMEText(body, 'plain'))
            
            # Create CSV attachment
            csv_content = self.create_csv_content(invalid_items, report_type)
            filename = f"invalid_{report_type}s_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
            
            attachment = MIMEBase('application', 'octet-stream')
            attachment.set_payload(csv_content.encode('utf-8'))
            encoders.encode_base64(attachment)
            attachment.add_header('Content-Disposition', f'attachment; filename={filename}')
            msg.attach(attachment)
            
            # Send email
            logger.info(f"Sending validation report to {self.to_address}...")
            
            # Port 465 requires SMTP_SSL, port 587 uses SMTP with STARTTLS
            if self.smtp_port == 465:
                server = smtplib.SMTP_SSL(self.smtp_host, self.smtp_port, timeout=30)
            elif self.use_tls:
                server = smtplib.SMTP(self.smtp_host, self.smtp_port, timeout=30)
                server.starttls()
            else:
                server = smtplib.SMTP(self.smtp_host, self.smtp_port, timeout=30)
            
            server.login(self.smtp_username, self.smtp_password)
            server.send_message(msg)
            server.quit()
            
            logger.info(f"✅ Validation report sent successfully ({len(invalid_items)} invalid {report_type}s)")
            return True
            
        except Exception as e:
            logger.error(f"Failed to send validation report: {e}")
            return False
    
    def send_consistency_report(self, report_output: str, checks_passed: bool) -> bool:
        """
        Send consistency check report email.
        
        Args:
            report_output: Full text output from the consistency check
            checks_passed: Whether all checks passed
            
        Returns:
            True if email sent successfully, False otherwise
        """
        if not self.enabled:
            logger.info("Email notifications disabled, skipping")
            return False
        
        try:
            # Create message
            msg = MIMEMultipart()
            msg['From'] = self.from_address
            msg['To'] = self.to_address
            
            if checks_passed:
                msg['Subject'] = '✅ Sync Consistency Check - All Checks Passed'
            else:
                msg['Subject'] = '❌ Sync Consistency Check - Issues Detected'
            
            # Format email body
            body_lines = []
            body_lines.append("Sync Consistency Check Report")
            body_lines.append("=" * 80)
            body_lines.append("")
            
            if checks_passed:
                body_lines.append("✅ ALL CHECKS PASSED - Data is consistent!")
            else:
                body_lines.append("❌ SOME CHECKS FAILED - Data inconsistency detected!")
            
            body_lines.append("")
            body_lines.append("Full Report:")
            body_lines.append("-" * 80)
            body_lines.append(report_output)
            body_lines.append("")
            
            if not checks_passed:
                body_lines.append("")
                body_lines.append("Recommended Actions:")
                body_lines.append("-" * 80)
                body_lines.append("1. Review the mismatches above")
                body_lines.append("2. Run: python3 reset_sync.py --yes")
                body_lines.append("3. Delete all transactions/categories in Actual Budget")
                body_lines.append("4. Run: python3 sync_from_cache.py")
            
            body_lines.append("")
            body_lines.append(f"Report generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            
            body = "\n".join(body_lines)
            msg.attach(MIMEText(body, 'plain'))
            
            # Send email
            logger.info(f"Sending consistency report to {self.to_address}...")
            
            # Use SSL connection for port 465
            if self.smtp_port == 465:
                server = smtplib.SMTP_SSL(self.smtp_host, self.smtp_port, timeout=30)
            else:
                server = smtplib.SMTP(self.smtp_host, self.smtp_port, timeout=30)
                if self.use_tls:
                    server.starttls()
            
            server.login(self.smtp_username, self.smtp_password)
            server.send_message(msg)
            server.quit()
            
            logger.info(f"✅ Consistency report sent successfully")
            return True
            
        except Exception as e:
            logger.error(f"Failed to send consistency report: {e}")
            return False
    
    @classmethod
    def from_config(cls, config) -> 'EmailNotifier':
        """
        Create EmailNotifier from config object.
        
        Args:
            config: Configuration object with email settings
            
        Returns:
            EmailNotifier instance
        """
        return cls(
            smtp_host=config.email_smtp_host,
            smtp_port=config.email_smtp_port,
            smtp_username=config.email_smtp_username,
            smtp_password=config.email_smtp_password,
            from_address=config.email_from,
            to_address=config.email_to,
            use_tls=config.email_use_tls,
            enabled=config.email_enabled
        )

