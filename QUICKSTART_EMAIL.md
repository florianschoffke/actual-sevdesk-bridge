# Quick Start: Email Notifications

## 🚀 5-Minute Setup

### Step 1: Update your `.env` file

Add these lines to your `.env`:

```env
# Email notifications
EMAIL_ENABLED=true
EMAIL_SMTP_HOST=smtp.gmail.com
EMAIL_SMTP_PORT=587
EMAIL_SMTP_USERNAME=your-email@gmail.com
EMAIL_SMTP_PASSWORD=your-app-password-here
EMAIL_FROM=your-email@gmail.com
EMAIL_TO=recipient@example.com
EMAIL_USE_TLS=true
```

### Step 2: Get a Gmail App Password

1. Go to https://myaccount.google.com/security
2. Click on "2-Step Verification" (enable it if not already)
3. Scroll down to "App passwords"
4. Select "Mail" and generate a password
5. Copy the 16-character password (spaces don't matter)
6. Paste it as `EMAIL_SMTP_PASSWORD` in your `.env`

### Step 3: Test it!

```bash
python3 test_email.py
```

You should see:
```
✅ Test email sent successfully!
   Check recipient@example.com for the email.
```

### Step 4: Run a sync

```bash
python3 main.py sync-vouchers
```

If there are any invalid vouchers, you'll automatically receive an email with a CSV report! 📧

## 📋 What You'll Receive

### Email Subject
```
Voucher Validation Failed - 3 Invalid Vouchers
```

### Email Body
```
Voucher validation completed with failures.

Summary:
- Total invalid vouchers: 3
- Report generated: 2025-10-21 14:30:00

Please review the attached CSV file for details...
```

### CSV Attachment
```csv
Voucher Number,Voucher Date,Status,Amount (EUR),Supplier,Cost Center ID,Cost Center Name,Validation Reason,Last Validated
2025-001,2025-10-20,1000,150.00,Test GmbH,,,Regular voucher missing cost center,2025-10-21T14:30:00
```

## 🔧 Other Email Providers

### Office 365
```env
EMAIL_SMTP_HOST=smtp.office365.com
EMAIL_SMTP_PORT=587
EMAIL_SMTP_USERNAME=you@company.com
EMAIL_SMTP_PASSWORD=your-password
```

### Custom SMTP
```env
EMAIL_SMTP_HOST=mail.yourcompany.com
EMAIL_SMTP_PORT=587
EMAIL_SMTP_USERNAME=smtp-user
EMAIL_SMTP_PASSWORD=smtp-password
```

## 🐛 Troubleshooting

**"Authentication failed"**
→ For Gmail, use App Password, not regular password

**"Connection refused"**
→ Check SMTP host and port are correct

**Email not received**
→ Check spam folder

See **EMAIL_NOTIFICATIONS.md** for detailed troubleshooting.

## 🎛️ Disable Anytime

```env
EMAIL_ENABLED=false
```

## 📚 Full Documentation

- **EMAIL_NOTIFICATIONS.md** - Complete setup guide
- **EMAIL_FEATURE_SUMMARY.md** - Technical implementation details

## ✅ Done!

You're all set! Your sync will now automatically email you when vouchers fail validation.
