# F-String Escaping in Code Generation — Pitfall Reference

## Context

The `data` CLI tool constructs Python scripts as f-string templates, then runs them via `subprocess.run([python, '-c', script, ...])`. Multiple providers (tushare, akshare, yfinance, etc.) each append their own code block to the script.

## The Pitfall: Single vs Double Braces in Nested F-Strings

When building Python code inside an outer f-string (`script += f'''...'''`):

| Intent | Write in data.py | Produces in script |
|--------|-----------------|-------------------|
| Interpolate variable NOW | `{token}` | actual token value |
| Defer to runtime (exec) | `{{ts_code}}` | `{ts_code}` |
| **BUG: forgot double-brace** | `{ts_code}` | **evaluated NOW → NameError** |

### Example (broken — data.py line 186, fixed 2026-05-11)

```python
# Inside script += f'''...'''
# BROKEN: single brace → Python tries to resolve ts_code during f-string evaluation
ts_code = f"{ts_code}.SH"   # NameError: name 'ts_code' is not defined

# FIXED: double brace → produces literal {ts_code} for runtime
ts_code = f"{{ts_code}}.SH"  # OK
```

### Why this is insidious

The error traceback points to `data.py line 186` (inside `call_provider`), **not** the subprocess. This means the script never even ran — it failed during construction. Key diagnostic signal:

- **Error in subprocess** → `json.dumps({"error": ...})` in stdout or stderr from subprocess
- **Error in data.py** → Python traceback from data.py itself → **check f-string escaping first**

## Secondary Pitfall: Parameter Propagation Gap

`fetch(source, params)` passes `source` as a separate argument, but `call_provider` originally only looked at `params.get('source', '')`. Since `params` had `{'source': 'stock'}` from the CLI parser, this appeared to work — but if `params` had no `source` key (e.g., from a different call path), argv[1] would be empty, causing the generated script's if/elif chain to miss all conditions and fall through to an unexpected branch.

**Fix:** Pass `source` explicitly to `call_provider` and use `params.get('source') or source` as the arg.

## Diagnosis Checklist for `data` CLI Failures

1. `data status` — check provider health first
2. `data fetch stock --symbol 600519` — smoke test with known liquid symbol
3. Read the traceback:
   - Traceback in **data.py** (not subprocess) → f-string construction error → check braces
   - `json.dumps({"error": ...})` in output → subprocess ran but provider failed → check token, network, API
4. If condition chain seems wrong, add `print(f"DEBUG source={source!r}", file=sys.stderr)` in the generated script
5. Isolate with a standalone test script (as done in this session with `/tmp/test_tushare_script.py`)
