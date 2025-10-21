# Email Notification Feature - Implementation Summary

## ✅ What Was Added

Email notifications are now automatically sent when voucher validation fails during sync. This helps you stay informed about vouchers that need correction without manually checking logs.

## 📁 New Files Created

1. **`src/notifications/email_notifier.py`** - Email notification module
   - Creates CSV reports from invalid vouchers
   - Sends email with attachment via SMTP
   - Configurable from settings

2. **`src/notifications/__init__.py`** - Package initialization
   - Exports `EmailNotifier` class

3. **`EMAIL_NOTIFICATIONS.md`** - Complete documentation
   - Setup instructions for Gmail, Office 365, and other providers
   - Configuration options explained
   - Troubleshooting guide
   - Security notes

4. **`test_email.py`** - Test script
   - Validates email configuration
   - Sends test email with sample data
   - Helps debug email setup issues

## 🔧 Modified Files

1. **`.env`** - Added email configuration:
   ```env
   EMAIL_ENABLED=true
   EMAIL_SMTP_HOST=smtp.gmail.com
   EMAIL_SMTP_PORT=587
   EMAIL_SMTP_USERNAME=your-email@gmail.com
   EMAIL_SMTP_PASSWORD=your-app-password
   EMAIL_FROM=your-email@gmail.com
   EMAIL_TO=recipient@example.com
   EMAIL_USE_TLS=true
   ```

2. **`src/config/settings.py`** - Added email settings:
   - Reads email configuration from environment variables
   - Provides defaults for optional settings
   - Validates required fields

3. **`src/storage/database.py`** - Added new method:
   - `get_invalid_vouchers()` - Returns full details of invalid vouchers for reporting
   - Includes all fields needed for CSV export

4. **`src/sync/vouchers.py`** - Integrated email notifications:
   - Imports `EmailNotifier`
   - Checks for invalid vouchers after sync
   - Sends email if invalid vouchers exist
   - Adds `'invalid': count` to return stats

5. **`README.md`** - Updated safety features section:
   - Mentions email notifications
   - Links to EMAIL_NOTIFICATIONS.md

## 🎯 How It Works

### During Sync
```
1. Sync vouchers from SevDesk
2. Validate each voucher
3. Mark validation status in database
4. Sync valid vouchers to Actual Budget
5. Check if invalid vouchers exist
6. If invalid vouchers exist AND email enabled:
   → Generate CSV report
   → Send email with attachment
```

### Email Content
- **Subject**: "Voucher Validation Failed - X Invalid Vouchers"
- **Body**: Summary with count, timestamp, and common issues
- **Attachment**: CSV file with full details

### CSV Columns
- Voucher Number
- Voucher Date
- Status
- Amount (EUR)
- Supplier
- Cost Center ID
- Cost Center Name
- Validation Reason
- Last Validated

## 📧 Setup Instructions

### Quick Setup (Gmail)

1. **Edit `.env`**:
   ```env
   EMAIL_ENABLED=true
   EMAIL_SMTP_HOST=smtp.gmail.com
   EMAIL_SMTP_PORT=587
   EMAIL_SMTP_USERNAME=myemail@gmail.com
   EMAIL_SMTP_PASSWORD=abcd efgh ijkl mnop  # App Password, not regular password!
   EMAIL_FROM=myemail@gmail.com
   EMAIL_TO=recipient@example.com
   EMAIL_USE_TLS=true
   ```

2. **Create Gmail App Password**:
   - Go to Google Account → Security → 2-Step Verification
   - Scroll to "App passwords"
   - Generate password for "Mail"
   - Use the 16-character password in `.env`

3. **Test the setup**:
   ```bash
   python3 test_email.py
   ```

4. **Run a sync**:
   ```bash
   python3 main.py sync-vouchers
   ```

If there are invalid vouchers, you'll receive an email!

### Other Email Providers

See **EMAIL_NOTIFICATIONS.md** for detailed instructions for:
- Office 365 / Outlook
- Custom SMTP servers
- Advanced configuration

## 🧪 Testing

Run the test script to verify your email configuration:

```bash
python3 test_email.py
```

This will:
- Check email configuration
- Create 2 test vouchers
- Send a test email with CSV attachment
- Show success/failure with troubleshooting tips

## 🔒 Security Notes

- **Never commit `.env` to git** - it contains credentials
- Use app-specific passwords when available
- Restrict file permissions: `chmod 600 .env`
- Consider using a dedicated email account for notifications

## 🐳 Docker Deployment

When running in Docker, pass email settings as environment variables:

```yaml
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

## 🎛️ Disabling Notifications

To disable without removing configuration:

```env
EMAIL_ENABLED=false
```

## 🐛 Troubleshooting

### Authentication Failed
- For Gmail: Use App Password, not regular password
- Verify 2-Step Verification is enabled
- Double-check username and password

### Connection Issues
- Verify SMTP host and port
- Check firewall allows SMTP connections
- Try port 465 with `EMAIL_USE_TLS=false` if 587 fails

### Email Not Received
- Check spam/junk folder
- Verify recipient address is correct
- Confirm sender address is valid

See **EMAIL_NOTIFICATIONS.md** for more troubleshooting tips.

## 📊 Return Values

The sync now includes invalid voucher count in stats:

```python
{
    'synced': 42,      # Successfully synced
    'created': 30,     # New transactions
    'updated': 12,     # Updated transactions
    'skipped': 15,     # Already synced
    'failed': 3,       # Failed to sync
    'validated': 50,   # Total validated
    'invalid': 3       # Failed validation (will trigger email)
}
```

## ✨ Benefits

1. **Proactive Monitoring**: Know immediately when vouchers fail validation
2. **Detailed Reports**: CSV attachment has all details needed for correction
3. **Self-Healing**: Invalid vouchers auto-revalidated on next sync once fixed
4. **No Manual Checking**: No need to check logs after each sync
5. **Audit Trail**: Email history provides audit trail of validation failures
6. **Flexible**: Easy to enable/disable, works with any SMTP provider

## 🎉 Ready to Use!

The feature is fully integrated and ready to use. Just:
1. Configure email settings in `.env`
2. Test with `python3 test_email.py`
3. Run your normal sync: `python3 main.py sync-vouchers`

You'll automatically receive emails when validation fails! 📧
