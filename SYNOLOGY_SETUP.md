# Synology Container Manager Setup Guide

This guide shows how to import and run the pre-built Docker image in Synology Container Manager (DSM 7.2+).

## 📦 Step 1: Build and Export Image (on your computer)

```bash
# Build and export the Docker image
./build-for-synology.sh

# This creates: docker-image/actual-sevdesk-bridge.tar.gz
```

## 📤 Step 2: Upload Image to Synology

### Via Synology Web UI:

1. **Open DSM** → **Container Manager**
2. Go to **Image** tab
3. Click **Add** → **Add from File**
4. Upload `docker-image/actual-sevdesk-bridge.tar.gz`
5. Wait for import to complete
6. Verify image appears as `actual-sevdesk-bridge:latest`

### Via SSH (Alternative):

```bash
# Copy image to Synology
scp docker-image/actual-sevdesk-bridge.tar.gz admin@your-synology-ip:/tmp/

# SSH into Synology
ssh admin@your-synology-ip

# Load the image
sudo docker load -i /tmp/actual-sevdesk-bridge.tar.gz

# Clean up
rm /tmp/actual-sevdesk-bridge.tar.gz
```

## 🎛️ Step 3: Prepare Configuration on Synology

1. **Create directory in File Station:**
   ```
   /docker/actual-sevdesk-bridge/
   ```

2. **Create data subdirectory:**
   ```
   /docker/actual-sevdesk-bridge/data/
   ```

3. **Upload your `.env` file** to `/docker/actual-sevdesk-bridge/.env`
   - Use File Station to upload
   - Or create via SSH:
   ```bash
   sudo nano /volume1/docker/actual-sevdesk-bridge/.env
   ```

## 🚀 Step 4: Create Container in Container Manager

### Via Web UI:

1. **Go to Container tab** → Click **Create**

2. **Select Image:**
   - Choose `actual-sevdesk-bridge:latest`
   - Click **Next**

3. **Container Settings:**
   - Container name: `actual-sevdesk-bridge`
   - Enable auto-restart: ✅
   - Click **Advanced Settings**

4. **Volume Settings (Important!):**
   - Click **Add Folder**
   - Select: `/docker/actual-sevdesk-bridge/data`
   - Mount path: `/app/data`
   - Read/Write: ✅

5. **Environment Variables:**
   Add all variables from your `.env` file:

   | Variable | Example Value |
   |----------|---------------|
   | `SEVDESK_API_KEY` | your_api_key |
   | `ACTUAL_BUDGET_URL` | http://192.168.1.100:5006 |
   | `ACTUAL_BUDGET_PASSWORD` | your_password |
   | `ACTUAL_BUDGET_FILE_ID` | My Budget |
   | `ACTUAL_BUDGET_VERIFY_SSL` | true |
   | `ACTUAL_ACCOUNT_NAME` | EGB Funds |
   | `LOG_LEVEL` | INFO |
   | `EMAIL_ENABLED` | true |
   | `EMAIL_SMTP_HOST` | smtp.example.com |
   | `EMAIL_SMTP_PORT` | 587 |
   | `EMAIL_SMTP_USERNAME` | your_email |
   | `EMAIL_SMTP_PASSWORD` | your_password |
   | `EMAIL_FROM` | sender@example.com |
   | `EMAIL_TO` | recipient@example.com |
   | `EMAIL_USE_TLS` | true |

6. **Execution Command:**
   - Command: `sh`
   - Arguments: 
     ```
     -c
     while true; do python3 main.py sync-all && python3 verify_sync.py; sleep 3600; done
     ```

7. Click **Done** and **Start** the container

### Via SSH (Alternative):

```bash
# Create container with docker run
sudo docker run -d \
  --name actual-sevdesk-bridge \
  --restart unless-stopped \
  -v /volume1/docker/actual-sevdesk-bridge/data:/app/data \
  -e SEVDESK_API_KEY="your_api_key" \
  -e ACTUAL_BUDGET_URL="http://192.168.1.100:5006" \
  -e ACTUAL_BUDGET_PASSWORD="your_password" \
  -e ACTUAL_BUDGET_FILE_ID="My Budget" \
  -e ACTUAL_BUDGET_VERIFY_SSL="true" \
  -e ACTUAL_ACCOUNT_NAME="EGB Funds" \
  -e LOG_LEVEL="INFO" \
  -e EMAIL_ENABLED="true" \
  -e EMAIL_SMTP_HOST="smtp.example.com" \
  -e EMAIL_SMTP_PORT="587" \
  -e EMAIL_SMTP_USERNAME="your_email" \
  -e EMAIL_SMTP_PASSWORD="your_password" \
  -e EMAIL_FROM="sender@example.com" \
  -e EMAIL_TO="recipient@example.com" \
  -e EMAIL_USE_TLS="true" \
  actual-sevdesk-bridge:latest \
  sh -c "while true; do python3 main.py sync-all && python3 verify_sync.py; sleep 3600; done"
```

## 📊 Step 5: Verify Container is Running

### Via Container Manager:
- Check container status shows **Running** ✅
- Click **Details** → **Log** to view sync activity

### Via SSH:
```bash
# Check container status
sudo docker ps | grep actual-sevdesk-bridge

# View logs
sudo docker logs -f actual-sevdesk-bridge

# Check last 50 lines
sudo docker logs --tail 50 actual-sevdesk-bridge
```

## 🔧 Common Operations

### View Logs:
```bash
sudo docker logs -f actual-sevdesk-bridge
```

### Restart Container:
```bash
sudo docker restart actual-sevdesk-bridge
```

### Stop Container:
```bash
sudo docker stop actual-sevdesk-bridge
```

### Remove Container (keeps image):
```bash
sudo docker rm actual-sevdesk-bridge
```

### Run Manual Sync:
```bash
sudo docker exec actual-sevdesk-bridge python3 main.py sync-all
```

### Run Verification:
```bash
sudo docker exec actual-sevdesk-bridge python3 verify_sync.py
```

### Access Container Shell:
```bash
sudo docker exec -it actual-sevdesk-bridge /bin/bash
```

## 🔄 Updating the Container

When you have a new version:

1. **Build new image** on your computer:
   ```bash
   ./build-for-synology.sh
   ```

2. **Upload new tar.gz** to Synology

3. **Stop and remove old container:**
   ```bash
   sudo docker stop actual-sevdesk-bridge
   sudo docker rm actual-sevdesk-bridge
   ```

4. **Remove old image:**
   ```bash
   sudo docker rmi actual-sevdesk-bridge:latest
   ```

5. **Load new image:**
   ```bash
   sudo docker load -i /tmp/actual-sevdesk-bridge.tar.gz
   ```

6. **Create new container** (repeat Step 4)

**Note:** Your data in `/volume1/docker/actual-sevdesk-bridge/data/` is preserved!

## 🗂️ Data Backup

Your sync state is stored in `/volume1/docker/actual-sevdesk-bridge/data/sync_state.db`

To backup:
```bash
# Via SSH
sudo cp /volume1/docker/actual-sevdesk-bridge/data/sync_state.db \
       /volume1/backups/sync_state.db.$(date +%Y%m%d)

# Or use File Station to copy the file
```

## 🐛 Troubleshooting

### Container exits immediately:
```bash
# Check logs for errors
sudo docker logs actual-sevdesk-bridge

# Common issues:
# - Missing environment variables
# - Wrong Actual Budget URL (use IP, not localhost)
# - Invalid credentials
```

### Cannot connect to Actual Budget:
- Make sure `ACTUAL_BUDGET_URL` uses Synology's IP address
- Check firewall allows port 5006
- Verify Actual Budget is running

### Email not sending:
- Check SMTP credentials in environment variables
- For Gmail: Use App Password, not regular password
- Verify `EMAIL_ENABLED=true`

### Database locked errors:
- Only one container should access the data directory
- Stop any duplicate containers:
  ```bash
  sudo docker ps -a | grep actual-sevdesk-bridge
  ```

## 📋 Sync Schedule

Default: Every hour (3600 seconds)

To change:
1. Stop container
2. Edit the command's `sleep` value:
   - `sleep 1800` = 30 minutes
   - `sleep 7200` = 2 hours  
   - `sleep 86400` = 24 hours (daily)
3. Recreate container with new command

## ✅ Verification

After first sync:
```bash
# Check logs for success
sudo docker logs actual-sevdesk-bridge

# Look for:
# ✅ Categories synced: X
# ✅ Vouchers synced: Y
# ✅ ALL CHECKS PASSED - Data is consistent!
```
