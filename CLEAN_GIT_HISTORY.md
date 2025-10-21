# Cleaning Git History - Remove Passwords from Commits

## ⚠️ Problem

The `.env` file with passwords was committed in the Git history. Even though it was later deleted, it still exists in old commits.

## ✅ Solution

I've created a script to completely remove Git history and start fresh.

## 🚀 Quick Method - Run the Script

```bash
./clean_git_history.sh
```

This will:
1. Save your remote URL
2. Delete the `.git` directory (removes ALL history)
3. Initialize a new Git repository
4. Create a fresh initial commit
5. Re-add your remote

Then force push to GitHub:
```bash
git push -f origin main
```

## 📋 Manual Method (if you prefer)

If you want to do it manually step-by-step:

### Step 1: Remove Git directory
```bash
rm -rf .git
```

### Step 2: Initialize fresh repository
```bash
git init
```

### Step 3: Add all files
```bash
git add .
```

### Step 4: Create initial commit
```bash
git commit -m "Initial commit (history cleaned)"
```

### Step 5: Re-add remote
```bash
git remote add origin https://github.com/florianschoffke/actual-sevdesk-bridge.git
```

### Step 6: Force push to GitHub
```bash
git push -f origin main
```

## ⚠️ IMPORTANT After Force Push

### For You
- The remote repository now has clean history
- Old commits with passwords are gone from GitHub
- Anyone viewing the repo won't see the passwords

### For Collaborators
If anyone else cloned this repository, they need to:

1. **Delete their local copy**
   ```bash
   rm -rf actual-sevdesk-bridge
   ```

2. **Clone fresh**
   ```bash
   git clone https://github.com/florianschoffke/actual-sevdesk-bridge.git
   ```

Their old local copy still has the history with passwords!

## 🔒 Security Best Practices Going Forward

### 1. `.env` is already in `.gitignore` ✅
The file is properly excluded. Just never use `git add -f .env`

### 2. Check before committing
```bash
git status  # Make sure .env isn't listed
```

### 3. If you accidentally stage .env
```bash
git reset HEAD .env  # Unstage it immediately
```

### 4. Use .env.example for templates
Always commit `.env.example` with placeholder values, never the real `.env`

### 5. Rotate compromised credentials
Since the passwords were in public history, consider:
- Changing your SevDesk API key
- Changing your Actual Budget password
- Updating email SMTP password

You can do this in the SevDesk and Actual Budget admin panels.

## 🧪 Verify It Worked

After force pushing, check GitHub:

1. Go to: https://github.com/florianschoffke/actual-sevdesk-bridge/commits/main
2. You should see only ONE commit: "Initial commit (history cleaned)"
3. Click through files - no passwords should be visible

## 📊 What Gets Removed

**Removed:**
- All old commits (including those with passwords)
- Entire commit history
- All branches except main
- All tags

**Kept:**
- All current files (latest version)
- Your working directory
- Your remote URL
- `.gitignore` configuration

## ❓ FAQ

**Q: Will this break anything?**
A: No, all your files stay exactly as they are. Only Git history is removed.

**Q: Can I undo this?**
A: Not after force pushing. The old history is permanently deleted from GitHub.

**Q: What if someone already cloned the repo?**
A: Their local copy still has the old history. They need to delete and re-clone.

**Q: Do I need to do anything else?**
A: Consider rotating any passwords that were exposed in the old commits.

**Q: Will this affect my database?**
A: No, `data/sync_state.db` is not affected. Only Git history changes.

## ✅ Checklist

- [ ] Run `./clean_git_history.sh` or manual steps
- [ ] Force push: `git push -f origin main`
- [ ] Verify on GitHub that only one commit exists
- [ ] (Optional) Rotate exposed credentials
- [ ] (If collaborators exist) Tell them to delete and re-clone
- [ ] Delete this instruction file: `rm CLEAN_GIT_HISTORY.md clean_git_history.sh`

## 🎉 Done!

Your repository now has a clean history with no passwords! 🔒
