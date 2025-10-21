# Email Notifications for Validation Failures

The sync system can automatically send email notifications when voucher validation fails. This helps you stay informed about vouchers that need correction without having to manually check the sync logs.

## How It Works

After each voucher sync completes:
1. The system checks if any vouchers failed validation
2. If invalid vouchers exist and email is enabled, it generates a CSV report
3. An email is sent with:
   - Summary of how many vouchers failed
   - Attached CSV file with full details
   - Timestamp of when the report was generated

## Configuration

Add the following settings to your `.env` file:

```env
# Email notifications for validation failures
EMAIL_ENABLED=true
EMAIL_SMTP_HOST=smtp.gmail.com
EMAIL_SMTP_PORT=587
EMAIL_SMTP_USERNAME=your-email@gmail.com
EMAIL_SMTP_PASSWORD=your-app-password
EMAIL_FROM=your-email@gmail.com
EMAIL_TO=recipient@example.com
EMAIL_USE_TLS=true
```

### Configuration Options

- `EMAIL_ENABLED`: Set to `true` to enable email notifications, `false` to disable
- `EMAIL_SMTP_HOST`: SMTP server hostname (e.g., `smtp.gmail.com`, `smtp.office365.com`)
- `EMAIL_SMTP_PORT`: SMTP server port (usually `587` for TLS, `465` for SSL)
- `EMAIL_SMTP_USERNAME`: Username for SMTP authentication
- `EMAIL_SMTP_PASSWORD`: Password for SMTP authentication
- `EMAIL_FROM`: Sender email address
- `EMAIL_TO`: Recipient email address (can be different from sender)
- `EMAIL_USE_TLS`: Set to `true` to use TLS encryption (recommended)

## Gmail Setup

If using Gmail, you need to create an **App Password** (not your regular Gmail password):

1. Go to your Google Account settings
2. Navigate to Security → 2-Step Verification
3. Scroll down to "App passwords"
4. Generate a new app password for "Mail"
5. Use this 16-character password in `EMAIL_SMTP_PASSWORD`

Example Gmail configuration:
```env
EMAIL_ENABLED=true
EMAIL_SMTP_HOST=smtp.gmail.com
EMAIL_SMTP_PORT=587
EMAIL_SMTP_USERNAME=myemail@gmail.com
EMAIL_SMTP_PASSWORD=abcd efgh ijkl mnop
EMAIL_FROM=myemail@gmail.com
EMAIL_TO=recipient@example.com
EMAIL_USE_TLS=true
```

## Office 365 / Outlook Setup

Example configuration for Office 365:
```env
EMAIL_ENABLED=true
EMAIL_SMTP_HOST=smtp.office365.com
EMAIL_SMTP_PORT=587
EMAIL_SMTP_USERNAME=myemail@company.com
EMAIL_SMTP_PASSWORD=your-password
EMAIL_FROM=myemail@company.com
EMAIL_TO=recipient@example.com
EMAIL_USE_TLS=true
```

## CSV Report Format

The attached CSV file contains the following columns:

| Column | Description |
|--------|-------------|
| Voucher Number | SevDesk voucher number |
| Voucher Date | Date of the voucher |
| Status | Voucher status code |
| Amount (EUR) | Total amount |
| Supplier | Supplier name |
| Cost Center ID | Cost center ID (if assigned) |
| Cost Center Name | Cost center name (if assigned) |
| Validation Reason | Why the voucher failed validation |
| Last Validated | When the voucher was last validated |

## Email Content

Example email:

```
Subject: Voucher Validation Failed - 5 Invalid Vouchers

Voucher validation completed with failures.

Summary:
- Total invalid vouchers: 5
- Report generated: 2025-10-21 14:30:00

Please review the attached CSV file for details on which vouchers need correction.

Common validation issues:
- Regular vouchers missing cost center assignment
- Geldtransit vouchers incorrectly assigned cost centers
- Other accounting type mismatches

The system will automatically re-validate these vouchers on the next sync once corrected.
```

## Testing Email Setup

To test if your email configuration works, you can temporarily set `EMAIL_ENABLED=true` and run a sync:

```bash
python3 main.py sync-vouchers --limit 10
```

If there are no invalid vouchers, you can create a test voucher in SevDesk without a cost center to trigger the validation failure and email.

## Disabling Email Notifications

To disable email notifications without removing the configuration:

```env
EMAIL_ENABLED=false
```

The sync will continue to work normally, but no emails will be sent.

## Troubleshooting

### "Authentication failed"
- Double-check your username and password
- For Gmail, make sure you're using an App Password, not your regular password
- Verify 2-Step Verification is enabled for Gmail

### "Connection refused" or "Connection timeout"
- Check that `EMAIL_SMTP_HOST` and `EMAIL_SMTP_PORT` are correct
- Verify your firewall allows outbound SMTP connections
- Try using port `465` with `EMAIL_USE_TLS=false` if port 587 doesn't work

### Email sent but not received
- Check spam/junk folder
- Verify `EMAIL_TO` address is correct
- Check that `EMAIL_FROM` is a valid sender address

### Certificate errors
- Make sure `EMAIL_USE_TLS=true` is set correctly
- Some SMTP servers may require SSL (port 465) instead of TLS (port 587)

## Security Notes

- **Never commit your `.env` file to version control** - it contains sensitive credentials
- Use app-specific passwords when available (Gmail, Outlook, etc.)
- Consider using a dedicated email account for automated notifications
- Restrict access to the `.env` file: `chmod 600 .env`

## Docker Deployment

When running in Docker, make sure to:
1. Mount or copy the `.env` file into the container
2. Or pass email settings as environment variables in `docker-compose.yml`:

```yaml
services:
  sync:
    image: your-sync-image
    environment:
      - EMAIL_ENABLED=true
      - EMAIL_SMTP_HOST=smtp.gmail.com
      - EMAIL_SMTP_PORT=587
      - EMAIL_SMTP_USERNAME=${EMAIL_SMTP_USERNAME}
      - EMAIL_SMTP_PASSWORD=${EMAIL_SMTP_PASSWORD}
      - EMAIL_FROM=${EMAIL_FROM}
      - EMAIL_TO=${EMAIL_TO}
      - EMAIL_USE_TLS=true
```
