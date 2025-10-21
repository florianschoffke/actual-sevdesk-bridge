#!/bin/bash
# Build and export Docker image for Synology Container Manager

set -e

echo "🐳 Building Docker image for Synology..."

# Build the image
docker build -t actual-sevdesk-bridge:latest .

# Create export directory
mkdir -p docker-image

# Export the image as a tar file
echo "📦 Exporting image to tar file..."
docker save -o docker-image/actual-sevdesk-bridge.tar actual-sevdesk-bridge:latest

# Compress the tar file to reduce size
echo "🗜️  Compressing image..."
gzip -f docker-image/actual-sevdesk-bridge.tar

echo "✅ Image exported successfully!"
echo ""
echo "📁 File location: docker-image/actual-sevdesk-bridge.tar.gz"
echo "📊 File size: $(du -h docker-image/actual-sevdesk-bridge.tar.gz | cut -f1)"
echo ""
echo "📤 Next steps:"
echo "1. Copy docker-image/actual-sevdesk-bridge.tar.gz to your computer"
echo "2. Open Synology Container Manager"
echo "3. Go to 'Image' → 'Add' → 'Add from File'"
echo "4. Upload actual-sevdesk-bridge.tar.gz"
echo "5. After import, follow SYNOLOGY_SETUP.md to create and run the container"
