# 券商对接快速指南 (v8.10)

> broker_gateway.py 支持 paper / xtquant / easytrader 三种模式

## 支持券商一览

### QMT / xtquant（首选）

需券商 QMT 客户端，从安装目录复制 `xtquant` 到 Python 环境。接口官方维护，不依赖页面爬虫。

| 券商 | 门槛 | 备注 |
|:--|:--|:--|
| **招商证券** ✅ | ~50万 | 官方QMT客户端，生态成熟 |
| 国金证券 | ~50万 | 量化生态最成熟 |
| 国信证券 | ~50万 | MiniQMT支持 |
| 中泰证券 | ~30万 | XTP接口可选 |
| 华鑫证券 | ~10万 | 低门槛明星 |
| **光大证券** | ~50万(QMT) / ~10万(PTrade) | 双平台可选，PTrade需额外适配 |
| 东方财富 | 无明确 | 终端内嵌QMT |

### easytrader（备用）

WEB自动化，免QMT权限但依赖页面结构。

| 券商 | 配置 |
|:--|:--|
| 华泰证券 | `easytrader.use('ht')` |
| 银河证券 | `easytrader.use('yh')` |
| 广发证券 | `easytrader.use('gf')` |
| 国金证券 | `easytrader.use('gjzq')` |

⚠️ 招商证券和光大证券不在 easytrader 默认支持列表中。

## 招商证券 QMT 配置流程

### 1. 开通权限
联系营业部开通「量化交易 QMT 权限」，获取 QMT 客户端下载链接。

### 2. 安装 xtquant
```bash
# 从 QMT 安装目录复制 xtquant 到 Python 环境
# Windows: C:\Program Files\xtquant\ 或 QMT\bin.x64\Lib\site-packages\xtquant\
scp -r xtquant/ pc@server:/tmp/
cp -r /tmp/xtquant /home/pc/.hermes/hermes-agent/venv/lib/python3.11/site-packages/

# 验证
python3 -c "from xtquant import xtdata; print('✅ xtquant 就绪')"
```

### 3. 验证连接
```bash
cd ~/hermes/profiles/xiaohong/scripts
python3 broker_gateway.py --live --status
# → ✅ xtquant 连接成功
```

### 4. 从 Paper 切换到 Live
```bash
# Paper 先行验证策略
python3 scripts/auto_executor.py --once --paper

# 切到实盘
python3 scripts/auto_executor.py --once --live
```

## 风控不变

Paper 和 Live 共享同一套风控检查：
```
信号 → 持仓≤9只 → 单股≤33.3% → 可用资金够 → R值≤2% → 下单
```
