# Wiki Auto-Ingest Cron Setup

Quick-reference for setting up automatic article ingestion from Obsidian Web Clipper.

## Flow

```
Browser → Web Clipper → Clippings/ in Obsidian vault
                             ↓ Obsidian Sync
                         ~/wiki/Clippings/ on server
                             ↓ Hermes cron (every 30min)
                         entities/ + concepts/ + log.md
```

## Cron Job Template

```json
{
  "action": "create",
  "name": "Wiki 自动消化新文章",
  "schedule": "*/30 * * * *",
  "deliver": "local",
  "skills": ["llm-wiki"],
  "enabled_toolsets": ["terminal", "file", "search_files", "skills"],
  "prompt": "Auto-ingest new articles from ~/wiki/Clippings/ and ~/wiki/raw/articles/ into the LLM Wiki.\n\nIMPORTANT: The folder is 'Clippings' (capital C), not 'clippings'. Check both.\n\nSteps:\n1. List all .md files in ~/wiki/Clippings/ AND ~/wiki/raw/articles/ (also check ~/wiki/clippings/)\n2. For each file: if it already has 'ingested:' AND 'sha256:' in frontmatter → skip\n3. For unprocessed files:\n   a. Read the full content\n   b. Add wiki-compliant frontmatter: source_url, ingested, sha256\n   c. Determine domain from the 6-domain taxonomy\n   d. Extract entities/concepts, search existing pages\n   e. Create/update wiki pages per LLM Wiki ingest rules\n   f. Update ~/wiki/index.md and ~/wiki/log.md\n4. Move processed files from Clippings/ to ~/wiki/raw/articles/\n5. If no new files, exit silently."
}
```

## Common Issues

| Issue | Cause | Fix |
|-------|-------|-----|
| Sync stuck at "Connecting..." | `ob sync --continuous` hung | `pkill -f "ob sync"`, reset systemd, restart |
| Clippings folder empty on server | Obsidian not open on device | User must open Obsidian to trigger sync |
| Cron finds no files | Wrong folder name (Clippings vs clippings) | Check actual name with `ls ~/wiki/` |
