#!/bin/bash

# Script to remove Git history and reinitialize repository
# This removes all commits (including passwords in history) and starts fresh

echo "⚠️  This will PERMANENTLY remove all Git history!"
echo "   Make sure you have a backup if needed."
echo ""
read -p "Continue? (yes/no): " confirm

if [ "$confirm" != "yes" ]; then
    echo "Aborted."
    exit 1
fi

echo ""
echo "📋 Step 1: Saving remote URL..."
REMOTE_URL=$(git remote get-url origin 2>/dev/null)
echo "   Remote URL: $REMOTE_URL"

echo ""
echo "🗑️  Step 2: Removing .git directory..."
rm -rf .git

echo ""
echo "🆕 Step 3: Initializing new Git repository..."
git init

echo ""
echo "📝 Step 4: Adding all files..."
git add .

echo ""
echo "💾 Step 5: Creating initial commit..."
git commit -m "Initial commit (history cleaned)"

if [ -n "$REMOTE_URL" ]; then
    echo ""
    echo "🔗 Step 6: Adding remote..."
    git remote add origin "$REMOTE_URL"
    
    echo ""
    echo "⚠️  To push to GitHub, you'll need to force push:"
    echo "   git push -f origin main"
    echo ""
    echo "   This will REPLACE the remote history with the clean version."
else
    echo ""
    echo "ℹ️  No remote was configured."
fi

echo ""
echo "✅ Git history has been cleaned!"
echo "   Old commits with passwords have been removed."
echo ""
echo "⚠️  IMPORTANT: If you already pushed to GitHub:"
echo "   1. Run: git push -f origin main"
echo "   2. Anyone else who cloned this repo should delete their copy and re-clone"
echo ""
