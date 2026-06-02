# 进化引擎调试手册

## 故障模式 1: extract_changes 返回空

### 症状
```
📭 无可执行参数变更（诊断文件为空或无建议）
```
但 `review_diagnosis.json` 存在且有内容。

### 诊断步骤
```python
import evolution_engine
path = str(evolution_engine.DATA_DIR / 'kb' / 'review_diagnosis.json')
diag = evolution_engine.load_diagnosis(path)
print(type(diag))  # 应该是 list
print(diag[0].keys())  # 应含 root_causes / rule_changes_suggested
```

### 三重根因

| # | 问题 | 修复 |
|:--|:--|:--|
| 1 | 路径偏移：`DATA_DIR.parent/"kb"` → `DATA_DIR/"kb"` | 路径修正为 `DATA_DIR / "kb"` |
| 2 | 格式断层：诊断文件是 `list[{root_causes}]`，代码期望 `dict{rule_changes_suggested}` | 双格式兼容 |
| 3 | `return changes` 在补丁中被误删 | 补回 `return changes` |

### 验证
```bash
python3 evolution_engine.py --dry-run
# 应输出: 📋 读取到 N 条参数建议
```

## 故障模式 2: 沙箱 KeyError 'old_metric'

### 症状
```
KeyError: 'old_metric'
```
`sandbox_test()` 返回 dict 不含 `old_metric`。

### 修复
```python
# old
print(f"旧命中率 {test_result['old_metric']}% → ...")

# new
if passed:
    print(f"✅ 通过: {test_result.get('details', 'ok')}")
else:
    print(f"❌ 未通过: {test_result.get('details', '验证失败')}")
```

## 故障模式 3: 变更幅度超限

### 症状
```
❌ 连板排除阈值: 变更幅度 100% 超出上限 20%
```

### 原因
P0 手动修复已更改了参数（连板排除 1→2），进化引擎从旧 review_diagnosis 中读到同样的变更建议，安全边界拦截。**这是正确的保护行为**。

### 处理
待下次 LLM复盘生成不含已修复问题的 review_diagnosis 后，新变更将通过。

## 故障模式 4: 进化后自检异常

`evolve()` live 模式末尾自动调用 `system_health_check.py --fix`。若健康检查异常：
- 查看 `scripts/data/health_check_log.json` 历史
- 手动运行 `python3 system_health_check.py --fix` 定位
