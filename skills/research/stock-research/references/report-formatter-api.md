# Report Formatter API

位于 `~/.hermes/profiles/xiaohong/scripts/report_formatter.py`。

## Report 类

```python
from report_formatter import Report

r = Report(title="标题", icon="🔭", color="blue")
```

| 参数 | 类型 | 说明 |
|------|------|------|
| `title` | str | 报告标题 |
| `icon` | str | 标题前缀 emoji |
| `color` | str | 主题色：`blue/green/red/yellow/purple` |

> ⚠️ `__init__` **只接受三个参数**：`title`、`icon`、`color`。没有 `subtitle` 参数。日期等元信息用 `header_meta()` 追加。

## 链式方法

| 方法 | 参数 | 说明 |
|------|------|------|
| `.header_meta(**kwargs)` | 键值对 | 标题下方元信息行 |
| `.section(title)` | str | 章节标题（粗体 ▸ 前缀） |
| `.text(content)` | str | 文本段落 |
| `.kv(key, value, sub="")` | str×3 | 键值对行，sub 为灰色副文本 |
| `.table(headers, rows)` | list×2 | Markdown 表格 |
| `.divider()` | — | 分割线 `---` |
| `.alert(msg, level)` | str×2 | 颜色告警（critical🔴/warning🟡/info🔵） |
| `.footer(text)` | str | 斜体页脚 |
| `.markdown()` | — | 输出增强 Markdown（cron no_agent stdout） |
| `.card()` | — | 输出飞书交互卡片 JSON（带标题栏配色） |

## ⚠️ 常见陷阱

### 1. `header_meta()` 使用 kwargs，不是 positional args

```python
# ❌ 错误
r.header_meta('2026-06-02', '数据源: xxx')
# → TypeError: Report.header_meta() takes 1 positional argument but 3 were given

# ✅ 正确
r.header_meta(日期='2026-06-02', 数据源='xxx')
```

### 2. `section()` 只创建标题，不包含正文

```python
# ❌ 错误 — 正文被当参数传入
r.section('📌 一个判断', '这里是正文内容...')  # 第二个参数被忽略

# ✅ 正确 — section() 后接 text()
r.section('📌 一个判断')
r.text('这里是正文内容...')
```

### 3. 没有 `subtitle` 参数

```python
# ❌ 错误
r = Report(title='标题', subtitle='副标题', icon='🌅')
# → TypeError: Report.__init__() got an unexpected keyword argument 'subtitle'

# ✅ 正确 — 用 header_meta 追加元信息
r = Report(title='标题', icon='🌅')
r.header_meta(日期='2026-06-02', 版本='v8.0')
```

## 使用模式

**cron no_agent 脚本** → 调用 `.markdown()` 输出，stdout 自动投递：
```python
r = Report(title='弹药库风控', icon='🛡️', color='red')
r.header_meta(日期='20260602', 净值='1,250,000')
r.section('持仓概览')
r.text('今日持仓 3 只，总仓位 45%')
r.table(['代码', '名称', '盈亏'], [['300131', '英唐智控', '+42.4%']])
r.alert('双良节能止损触发', 'warning')
r.footer('安幕诺家族 · 弹药库 v4.1')
print(r.markdown())
```

**--push 模式** → 可输出 `.card()` JSON 用于飞书交互卡片。

## 飞书卡片效果

- `.card()` 生成带 `header.template` 配色的交互卡片
- 支持 `wide_screen_mode`
- `div` 块用 `lark_md` 渲染 Markdown
- `note` 元素做灰色页脚
- 颜色告警用 `<font color='red'>` 标签
