# Cron 脚本行号污染 · 诊断与修复手册

> 故障日期: 2026-06-04 | 影响: 22/26 脚本 | 修复版本: v8.10

## 症状

- 多个 cron job 的 `last_status` 显示 `error`
- 健康检查 `check_scout_sniper()` 读取输出文件显示 `ok`（因为输出文件存在且有内容）
- cron output 文件中包含 `script failed` / `exited with code 2`
- stderr 报错类似 `行 1: 1: 未找到命令` 每行一个

## 根因

cron_*.sh 文件内容被写入了**带行号前缀**的内容。每行开头为 `     N|`（空格+行号+管道符），导致：

```bash
     1|#!/bin/bash    # bash 尝试将 "1|#!/bin/bash" 作为管道执行
     2|# comment        # bash 尝试执行 "2|# comment"  
     3|cd /path          # bash 尝试执行 "3|cd /path"
```

shebang 无法被解析，所有行被当作命令执行，全部失败 → exit 2。

## 诊断方法

### 快速检测
```bash
# 检查首字符是否为 #!
xxd cron_scout.sh | head -3
# 正常: 00000000: 2321 2f62 696e 2f62 6173 680a  #!/bin/bash.
# 污染: 00000000: 2020 2020 2031 7c23 212f         1|#!/
```

### 批量扫描
```bash
cd ~/.hermes/profiles/xiaohong/scripts
for f in cron_*.sh; do
    first_char=$(head -c 1 "$f" | xxd -p)
    if [ "$first_char" != "23" ]; then
        echo "❌ $f - 被污染"
    fi
done
```

### 自动检测（已集成到健康检查 v1.2）
```python
python3 -c "
from system_health_check import check_cron_scripts
result = check_cron_scripts()
print(result['status'], result.get('corrupted', []))
"
# → ok / down ['cron_scout.sh', 'cron_ammo.sh', ...]
```

## 修复方法

```bash
# 批量清除行号前缀
cd ~/.hermes/profiles/xiaohong/scripts
for f in cron_*.sh; do
    sed -i 's/^[[:space:]]*[0-9]\+|//' "$f"
done

# 验证修复
for f in cron_*.sh; do
    bash -n "$f" && echo "✅ $f" || echo "❌ $f"
done
```

## 防范机制

`system_health_check.py` v1.2 新增：

- **第12维「📜 Cron脚本」**：遍历所有 `cron_*.sh`，读取前 20 字节，检测是否以 `#!` 开头。异常标记 `status: down`。
- **第6维「⚙️ Cron执行」**（增强）：扫描 `cron/output/*/` 下所有最近 24h 的输出文件，检测 `script failed` / `exited with code` 标记。发现脚本执行失败直接报警。

## 历史教训

- 健康检查**查产出物**而非**查管道**——产出物可能从破裂管道漏出，但只有查退出码才知道管道破了。
- 文件完整性检查应该是最基础的防线，不应依赖「产出物存在=健康」的推理。
- 此类问题一旦发生是**全系统性的**（22/26 脚本同时损坏），必须第一时间报警而非等人工发现。
