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
    
    def create_csv_content(self, invalid_vouchers: List[Dict[str, Any]]) -> str:
        """
        Create CSV content from invalid vouchers.
        
        Args:
            invalid_vouchers: List of invalid voucher dictionaries
            
        Returns:
            CSV content as string
        """
        output = StringIO()
        writer = csv.writer(output)
        
        # Write header
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
        
        # Write voucher data
        for voucher in invalid_vouchers:
            writer.writerow([
                voucher.get('voucher_number', ''),
                voucher.get('voucher_date', ''),
                voucher.get('status', ''),
                voucher.get('amount', ''),
                voucher.get('supplier_name', ''),
                voucher.get('cost_center_id', ''),
                voucher.get('cost_center_name', ''),
                voucher.get('validation_reason', ''),
                voucher.get('last_validated_at', '')
            ])
        
        return output.getvalue()
    
    def send_validation_report(self, invalid_vouchers: List[Dict[str, Any]]) -> bool:
        """
        Send email with invalid vouchers CSV attachment.
        
        Args:
            invalid_vouchers: List of invalid voucher dictionaries
            
        Returns:
            True if email sent successfully, False otherwise
        """
        if not self.enabled:
            logger.info("Email notifications disabled, skipping")
            return False
        
        if not invalid_vouchers:
            logger.info("No invalid vouchers to report")
            return True
        
        try:
            # Create message
            msg = MIMEMultipart()
            msg['From'] = self.from_address
            msg['To'] = self.to_address
            msg['Subject'] = f'Voucher Validation Failed - {len(invalid_vouchers)} Invalid Vouchers'
            
            # Create table preview (first 10 vouchers)
            preview_vouchers = invalid_vouchers[:10]
            table_lines = []
            table_lines.append("")
            table_lines.append("Invalid Vouchers:")
            table_lines.append("-" * 100)
            
            for v in preview_vouchers:
                voucher_id = v.get('id', '')
                voucher_num = v.get('voucher_number', 'N/A')
                date = v.get('voucher_date', 'N/A')
                amount = v.get('amount', 0)
                supplier = v.get('supplier_name', 'N/A') or 'N/A'
                reason = v.get('validation_reason', 'N/A')
                
                # Format with proper alignment
                table_lines.append(f"  Voucher:  {voucher_num}")
                table_lines.append(f"  ID:       {voucher_id}")
                table_lines.append(f"  Link:     https://my.sevdesk.de/ex/detail/id/{voucher_id}")
                table_lines.append(f"  Date:     {date}")
                table_lines.append(f"  Amount:   €{amount:,.2f}")
                table_lines.append(f"  Supplier: {supplier}")
                table_lines.append(f"  Reason:   {reason}")
                table_lines.append("-" * 100)
            
            if len(invalid_vouchers) > 10:
                table_lines.append(f"\n... and {len(invalid_vouchers) - 10} more voucher(s).")
                table_lines.append("See attached CSV for complete list.")
            
            table_preview = "\n".join(table_lines)
            
            # Email body
            body = f"""
Voucher validation completed with failures.

Summary:
- Total invalid vouchers: {len(invalid_vouchers)}
- Report generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

{table_preview}

Common validation issues:
- Regular vouchers missing cost center assignment
- Geldtransit vouchers incorrectly assigned cost centers
- Other accounting type mismatches

Please review the attached CSV file for complete details on which vouchers need correction.

The system will automatically re-validate these vouchers on the next sync once corrected.
"""
            msg.attach(MIMEText(body, 'plain'))
            
            # Create CSV attachment
            csv_content = self.create_csv_content(invalid_vouchers)
            filename = f"invalid_vouchers_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
            
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
            
            logger.info(f"✅ Validation report sent successfully ({len(invalid_vouchers)} invalid vouchers)")
            return True
            
        except Exception as e:
            logger.error(f"Failed to send validation report: {e}")
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
