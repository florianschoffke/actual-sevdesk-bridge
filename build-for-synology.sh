#!/bin/bash
# Build and export Docker image for Synology Container Manager

set -e

echo "🧹 Cleaning up old Docker images..."
docker image prune -f

echo "🐳 Building Docker image for Synology (AMD64 architecture)..."

# Build the image for AMD64/x86_64 architecture (Synology NAS compatibility)
# Note: This uses QEMU emulation on ARM64 Macs, which may be slower but ensures compatibility
docker build --platform linux/amd64 -t actual-sevdesk-bridge:latest .

# Create export directory
mkdir -p docker-image

# Export the image as a tar file
echo "📦 Exporting image to tar file..."
docker save -o docker-image/actual-sevdesk-bridge.tar actual-sevdesk-bridge:latest

# Compress the tar file to reduce size
echo "🗜️  Compressing image..."
gzip -f docker-image/actual-sevdesk-bridge.tar

# Copy to Downloads folder
echo "📋 Copying to Downloads folder..."
mv -f docker-image/actual-sevdesk-bridge.tar.gz ~/Downloads/

echo "✅ Image exported successfully!"
