# Multi-Domain Personal Knowledge Base Template

A reusable SCHEMA.md + tag taxonomy configuration for a general personal
knowledge base covering six common domains. Copy and adapt for your own wiki.

## .env Setup

```bash
# Both variables must point to the same directory:
WIKI_PATH=$HOME/wiki
OBSIDIAN_VAULT_PATH=$HOME/wiki
```

After adding these, restart the Hermes session or run `/reload`.

## Domain List

1. **AI/ML 应用技术** — models, frameworks, applied techniques, LLM, RAG, Agent
2. **产品规划设计** — product planning, UX design, roadmap, user research
3. **全栈开发** — full-stack, frontend, backend, DevOps, databases, cloud
4. **理财交易** — personal finance, investment, trading, market analysis
5. **企业管理** — leadership, operations, strategy, team management
6. **生活助理** — health, travel, productivity, hobbies, life hacks

## Tag Taxonomy (38 tags)

### AI/ML
`model` `framework` `llm` `rag` `agent` `training` `inference` `multimodal` `benchmark` `paper`

### Product Design
`product-strategy` `user-research` `ux-design` `roadmap` `prototype` `analytics` `growth` `competitive-analysis`

### Full-Stack Development
`frontend` `backend` `database` `devops` `cloud` `architecture` `security` `api` `testing`

### Finance & Trading
`investment` `trading` `market-analysis` `crypto` `risk-management` `tax` `portfolio`

### Enterprise Management
`leadership` `team-building` `operations` `strategy` `okr` `hiring` `communication` `culture`

### Life Assistant
`health` `travel` `productivity` `reading` `cooking` `fitness` `home` `hobby`

### Cross-Domain
`comparison` `tutorial` `opinion` `checklist` `reference`

## Domain-Specific Notes

- **AI/ML:** Fast-moving field — mark `confidence: medium` on single-source claims, revisit quarterly
- **Finance:** Never treat as financial advice — always flag `confidence: low` for predictions
- **Management:** Distinguish theory (sources) from personal experience (`opinion` tag)
- **Life:** Personal preference pages tagged `opinion` need no external sources

## Obsidian Setup

1. Open Obsidian → "Open folder as vault" → select `~/wiki`
2. Settings → Files & Links → Attachment folder path: `raw/assets`
3. Settings → Files & Links → enable "Wikilinks"
4. Install Dataview plugin for frontmatter queries

## index.md Section Template

The index is organized by domain + type (entities/concepts/comparisons/queries):

```
## {Domain Name}
### Entities
### Concepts
### Comparisons
### Queries
```
