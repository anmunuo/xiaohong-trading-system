# Obsidian Headless Sync Setup Reference

## Environment Details (from 2026-05-09 session)

| Item | Value |
|------|-------|
| obsidian-headless path | `/home/pc/.npm-global/bin/ob` |
| Node.js | v22.22.2 |
| Obsidian account | 27153343@qq.com |
| Remote vault | anmunuo (d1f2ae8c85b3e4d2ff9b0173c3d2876e) |
| Local vault path | ~/wiki |
| systemd service | `obsidian-wiki-sync.service` |
| Git backup remote | https://gitee.com/fandi365/wiki.git |

## Full Setup Sequence

```bash
# 1. Verify tools
node --version          # ≥22
which ob                # /home/pc/.npm-global/bin/ob
ob login                # Should show "Logged in as FD (27153343@qq.com)"

# 2. Check existing vaults
ob sync-list-remote     # Only "anmunuo" exists — vault limit reached

# 3. Connect wiki to existing vault
cd ~/wiki
ob sync-setup \
  --vault "anmunuo" \
  --password "<vault-encryption-password>" \
  --device-name "hermes-server"

# 4. Initial sync (will download all remote files + upload local)
ob sync

# 5. Continuous sync service
# Service file: ~/.config/systemd/user/obsidian-wiki-sync.service
systemctl --user daemon-reload
systemctl --user enable --now obsidian-wiki-sync.service
sudo loginctl enable-linger $USER

# 6. Verify
systemctl --user status obsidian-wiki-sync.service
# Should show "Fully synced" every 30s
```

## Gitee Git Backup Setup

```bash
cd ~/wiki
git init
git config user.email "27153343@qq.com"
git config user.name "FD"
git add -A && git commit -m "init"
git remote add origin https://fandi365:<token>@gitee.com/fandi365/wiki.git
git push -u origin main

# Auto-backup script: ~/wiki/.git-auto-backup.sh
# Hermes cron: hourly at 0 * * * *
```

## Lessons Learned

- GitHub is often unreachable from China → use Gitee
- Vault encryption password is NOT the Obsidian account password
- Free Obsidian accounts have a 1-vault limit
- First sync with hundreds of files may timeout; continuous sync handles the rest
- `--file-types` (image/audio/video/pdf) only filters attachments; .md always syncs
- Git push with URL-embedded token works for Gitee auth
