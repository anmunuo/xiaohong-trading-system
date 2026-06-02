---
name: architecture-diagram
description: "Dark-themed SVG architecture/cloud/infra diagrams as HTML."
version: 1.0.0
author: Cocoon AI (hello@cocoon-ai.com), ported by Hermes Agent
license: MIT
dependencies: []
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [architecture, diagrams, SVG, HTML, visualization, infrastructure, cloud]
    related_skills: [concept-diagrams, excalidraw]
---

# Architecture Diagram Skill

Generate professional technical architecture diagrams as standalone HTML files with inline SVG graphics. No external tools, no API keys, no rendering libraries.

**DEFAULT THEME: Light background (white/slate-50), dark text.** Only use dark theme if user explicitly requests "dark" or "暗色". Dark diagrams are hard to read in Feishu/Lark — user rejected them 2026-06-02.

**Also update the Scope section to note the Feishu preference:** This skill is the PRIMARY choice for Feishu architecture diagrams. Light-theme SVG renders clearly in Feishu/Lark. If the user says "architecture diagram" without specifying a style, use light theme by default.

## Scope

**Best suited for:**
- Software system architecture (frontend / backend / database layers)
- Cloud infrastructure (VPC, regions, subnets, managed services)
- Microservice / service-mesh topology
- Database + API map, deployment diagrams
- Anything with a tech-infra subject that fits a dark, grid-backed aesthetic

**Look elsewhere first for:**
- Physics, chemistry, math, biology, or other scientific subjects
- Physical objects (vehicles, hardware, anatomy, cross-sections)
- Floor plans, narrative journeys, educational / textbook-style visuals
- Hand-drawn whiteboard sketches (consider `excalidraw`)
- Animated explainers (consider an animation skill)

If a more specialized skill is available for the subject, prefer that. If none fits, this skill can also serve as a general SVG diagram fallback — the output will just carry the dark tech aesthetic described below.

Based on [Cocoon AI's architecture-diagram-generator](https://github.com/Cocoon-AI/architecture-diagram-generator) (MIT).

## Workflow

1. User describes their system architecture (components, connections, technologies)
2. Generate the HTML file following the design system below
3. Save with `write_file` to a `.html` file (e.g. `~/architecture-diagram.html`)
4. User opens in any browser — works offline, no dependencies

### Output Location

Save diagrams to a user-specified path, or default to the current working directory:
```
./[project-name]-architecture.html
```

### Preview

After saving, suggest the user open it:
```bash
# macOS
open ./my-architecture.html
# Linux
xdg-open ./my-architecture.html
```

## 用户主题偏好

**默认使用亮色白底主题（light theme）。** 暗色主题在飞书消息中不清晰，已被用户否决。

亮色主题规格：
- 背景: `#f8f9fa` (body), `#ffffff` (diagram card)
- 网格: `#e9ecef`
- 组件填充: 亮色半透明（如 `#d1fae5` / `#e0f2fe` / `#ede9fe` / `#fef3c7`）
- 文字: `#1a1a2e` (标题), `#374151` (正文), `#065f46` / `#0284c7` (强调)
- 边框: 保持语义颜色的 stroke，填充电改用亮色
- 卡片: 白底 + 浅灰边框 + 微阴影

语义色在亮色模式下的映射：
| 类型 | 填充 | 边框 | 文字 |
|------|------|------|------|
| Data Sources | `#e0f2fe` | `#0ea5e9` | `#0284c7` |
| Backend/Exec | `#d1fae5` | `#10b981` | `#065f46` |
| Data/KB | `#ede9fe` | `#8b5cf6` | `#5b21b6` |
| Parliament/Evo | `#fef3c7` | `#f59e0b` | `#b45309` |
| NEW features | `#fff7ed` | `#f97316` | `#c2410c` |
| Support | `#f8f9fa` | `#dee2e6` | `#868e96` |

模板参考：`templates/template-light.html`

### Theme Preference

**Default: Light theme (亮色白底).** Dark theme was rejected by user — "不要用暗色图不清晰，换成白底的亮色图". Generate light-themed diagrams unless the user explicitly asks for dark mode.

### Color Palette — Light Theme (preferred)

Use light fills with darker borders for readability:

| Component Type | Fill (Background) | Stroke (Hex) |
| :--- | :--- | :--- |
| **Data Sources** | `#e0f2fe` (light sky) | `#0ea5e9` (sky-500) |
| **Pipeline / Backend** | `#d1fae5` (light emerald) | `#10b981` (emerald-500) |
| **Data / KB** | `#ede9fe` (light violet) | `#8b5cf6` (violet-500) |
| **Parliament / Evolution** | `#fef3c7` (light amber) | `#f59e0b` (amber-500) |
| **New / Highlight** | `#fff7ed` (light orange) | `#f97316` (orange-500) |
| **Security** | `#fce7f3` (light rose) | `#e11d48` (rose-600) |
| **Execution Layer** | `#f1f5f9` (light slate) | `#cbd5e1` |

### Typography & Background (Light)
- **Font:** JetBrains Mono (Monospace), loaded from Google Fonts
- **Sizes:** 11-12px (Names), 9px (Sublabels), 8px (Annotations), 7px (Tiny labels)
- **Background:** `#f8f9fa` with a subtle 40px grid pattern `#e9ecef`
- **Text:** `#1a1a2e` (titles), `#374151` (body), `#64748b` (secondary)

**Grid Pattern:**
```svg
<pattern id="grid" width="40" height="40" patternUnits="userSpaceOnUse">
  <path d="M 40 0 L 0 0 0 40" fill="none" stroke="#e9ecef" stroke-width="0.5"/>
</pattern>
```

### Color Palette — Dark Theme (legacy, only if user explicitly requests)

| Component Type | Fill (rgba) | Stroke (Hex) |
| :--- | :--- | :--- |
| **Frontend** | `rgba(8, 51, 68, 0.4)` | `#22d3ee` (cyan-400) |
| **Backend** | `rgba(6, 78, 59, 0.4)` | `#34d399` (emerald-400) |
| **Database** | `rgba(76, 29, 149, 0.4)` | `#a78bfa` (violet-400) |
| **AWS/Cloud** | `rgba(120, 53, 15, 0.3)` | `#fbbf24` (amber-400) |
| **Security** | `rgba(136, 19, 55, 0.4)` | `#fb7185` (rose-400) |
| **Message Bus** | `rgba(251, 146, 60, 0.3)` | `#fb923c` (orange-400) |
| **External** | `rgba(30, 41, 59, 0.5)` | `#94a3b8` (slate-400) |

## Technical Implementation Details

### Component Rendering
Components are rounded rectangles (`rx="6"`) with 1.5px strokes. To prevent arrows from showing through semi-transparent fills, use a **double-rect masking technique**:
1. Draw an opaque background rect (`#0f172a`)
2. Draw the semi-transparent styled rect on top

### Connection Rules
- **Z-Order:** Draw arrows *early* in the SVG (after the grid) so they render behind component boxes
- **Arrowheads:** Defined via SVG markers
- **Security Flows:** Use dashed lines in rose color (`#fb7185`)
- **Boundaries:**
  - *Security Groups:* Dashed (`4,4`), rose color
  - *Regions:* Large dashed (`8,4`), amber color, `rx="12"`

### Spacing & Layout Logic
- **Standard Height:** 60px (Services); 80-120px (Large components)
- **Vertical Gap:** Minimum 40px between components
- **Message Buses:** Must be placed *in the gap* between services, not overlapping them
- **Legend Placement:** **CRITICAL.** Must be placed outside all boundary boxes. Calculate the lowest Y-coordinate of all boundaries and place the legend at least 20px below it.

## Document Structure

The generated HTML file follows a four-part layout:
1. **Header:** Title with a pulsing dot indicator and subtitle
2. **Main SVG:** The diagram contained within a rounded border card
3. **Summary Cards:** A grid of three cards below the diagram for high-level details
4. **Footer:** Minimal metadata

### Info Card Pattern
```html
<div class="card">
  <div class="card-header">
    <div class="card-dot cyan"></div>
    <h3>Title</h3>
  </div>
  <ul>
    <li>• Item one</li>
    <li>• Item two</li>
  </ul>
</div>
```

## Output Requirements
- **Single File:** One self-contained `.html` file
- **No External Dependencies:** All CSS and SVG must be inline (except Google Fonts)
- **No JavaScript:** Use pure CSS for any animations (like pulsing dots)
- **Compatibility:** Must render correctly in any modern web browser

## Template Reference

Load the full HTML template for the exact structure, CSS, and SVG component examples:

```
skill_view(name="architecture-diagram", file_path="templates/template.html")
```

The template contains working examples of every component type (frontend, backend, database, cloud, security), arrow styles (standard, dashed, curved), security groups, region boundaries, and the legend — use it as your structural reference when generating diagrams.
