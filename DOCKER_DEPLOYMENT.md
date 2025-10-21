# Docker Deployment on Synology NAS

This guide explains how to deploy the Actual-SevDesk Bridge on a Synology NAS using Docker.

## Prerequisites

1. **Synology NAS** with DSM 7.x
2. **Docker package** installed on Synology (via Package Center)
3. **SSH access** to your Synology (optional, but recommended)

## Deployment Steps

### Option 1: Using Synology Docker GUI

1. **Prepare the files:**
   ```bash
   # On your computer, copy your .env file:
   cp .env.example .env
   # Edit .env with your actual credentials
   ```

2. **Upload to Synology:**
   - Open File Station on your Synology
   - Create a folder: `/docker/actual-sevdesk-bridge`
   - Upload all files from this repository to that folder

3. **Create Container:**
   - Open Docker package on Synology
   - Go to "Image" tab → "Add" → "Add from Dockerfile"
   - Select the uploaded Dockerfile
   - Build the image (name it: `actual-sevdesk-bridge`)

4. **Run Container:**
   - Go to "Container" tab → "Create"
   - Select the `actual-sevdesk-bridge` image
   - Click "Advanced Settings":
     - **Volume:** Add folder `/docker/actual-sevdesk-bridge/data` → mount to `/app/data`
     - **Environment:** Add all variables from your `.env` file
     - **Auto-restart:** Enable
   - Click "Apply" and start the container

### Option 2: Using SSH and Docker Compose (Recommended)

1. **SSH into your Synology:**
   ```bash
   ssh admin@your-synology-ip
   ```

2. **Navigate to docker directory:**
   ```bash
   sudo mkdir -p /volume1/docker/actual-sevdesk-bridge
   cd /volume1/docker/actual-sevdesk-bridge
   ```

3. **Clone or upload the repository:**
   ```bash
   # Option A: Clone from git
   git clone https://github.com/florianschoffke/actual-sevdesk-bridge.git .
   
   # Option B: Upload files via SCP from your computer
   # scp -r * admin@your-synology-ip:/volume1/docker/actual-sevdesk-bridge/
   ```

4. **Create and configure .env file:**
   ```bash
   cp .env.example .env
   nano .env  # or use vi, or edit via File Station
   ```

5. **Build and start the container:**
   ```bash
   sudo docker-compose up -d --build
   ```

6. **Check logs:**
   ```bash
   sudo docker-compose logs -f
   ```

## Configuration

Edit your `.env` file with your actual credentials:

```bash
# Required
SEVDESK_API_KEY=your_api_key
ACTUAL_BUDGET_URL=http://your-actual-ip:5006
ACTUAL_BUDGET_PASSWORD=your_password
ACTUAL_BUDGET_FILE_ID=your_file_id

# Optional - Email notifications
EMAIL_ENABLED=true
EMAIL_SMTP_HOST=smtp.example.com
EMAIL_SMTP_PORT=587
EMAIL_SMTP_USERNAME=your_email
EMAIL_SMTP_PASSWORD=your_password
EMAIL_FROM=sender@example.com
EMAIL_TO=recipient@example.com
```

## Sync Schedule

The container runs:
- **Sync:** Every hour (`sync-all`)
- **Verification:** After each sync (`verify_sync.py`)
- **Email notifications:** Sent automatically on validation failures or inconsistencies

To change the schedule, modify the `command` in `docker-compose.yml`:

```yaml
# Example: Sync every 30 minutes
command: sh -c "while true; do python3 main.py sync-all && python3 verify_sync.py; sleep 1800; done"
```

## Manual Operations

To run manual commands inside the container:

```bash
# SSH into Synology first
cd /volume1/docker/actual-sevdesk-bridge

# Run a manual sync
sudo docker-compose exec actual-sevdesk-bridge python3 main.py sync-all

# Run verification
sudo docker-compose exec actual-sevdesk-bridge python3 verify_sync.py

# Reset sync state
sudo docker-compose exec actual-sevdesk-bridge python3 reset_sync.py --yes

# View logs
sudo docker-compose logs -f

# Restart container
sudo docker-compose restart
```

## Data Persistence

The SQLite database is stored in `/app/data` inside the container, which is mounted to `./data` on your Synology. This ensures:
- ✅ Data survives container restarts
- ✅ Easy backup of sync state
- ✅ Persistent voucher cache

## Backup

To backup your sync state:

```bash
# Via SSH
cp /volume1/docker/actual-sevdesk-bridge/data/sync_state.db /volume1/backups/

# Or via File Station
# Copy /docker/actual-sevdesk-bridge/data/sync_state.db to your backup location
```

## Troubleshooting

### Container won't start
```bash
# Check logs
sudo docker-compose logs

# Rebuild image
sudo docker-compose down
sudo docker-compose up -d --build
```

### Connection issues to Actual Budget
- Make sure `ACTUAL_BUDGET_URL` uses the correct IP (not `localhost`)
- If Actual Budget is on the same Synology, use the Synology's IP address
- Check firewall settings on port 5006

### Email not sending
- Verify SMTP credentials in `.env`
- For Gmail: Use an App Password, not your regular password
- For port 465: Make sure `EMAIL_USE_TLS=true`

## Updates

To update the bridge:

```bash
cd /volume1/docker/actual-sevdesk-bridge
git pull  # or upload new files
sudo docker-compose down
sudo docker-compose up -d --build
```

## Stop/Remove Container

```bash
# Stop container
sudo docker-compose stop

# Remove container (keeps data)
sudo docker-compose down

# Remove everything including data
sudo docker-compose down -v
```
