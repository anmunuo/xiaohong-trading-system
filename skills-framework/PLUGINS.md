# 小红 Skills 框架 v2 — 参照 JoelLewis finance_skills 插件架构升级
# =========================================================================
# 核心改进:
#   1. 分层插件架构 (core → wealth → trading → advisory)
#   2. 领域插件化 (每个插件独立安装、独立依赖)
#   3. 量化技能带 Python 脚本 / 知识技能纯 SKILL.md
#   4. 符号链接安装 + marketplace.json 注册
#   5. 风险衡量 + 资产类别 + 估值 + 组合构建 四大财富管理子域

schema_version: 2

# ═══════════════════════════════════════
# 插件注册表
# ═══════════════════════════════════════

plugins:
  # ── 核心层（所有插件的基础依赖）──
  - id: core
    name: 数学与统计基础
    version: 1.0.0
    description: 金融数学和统计基础——所有其他插件的隐式依赖
    skill_count: 3
    has_python: true
    skills:
      - return-calculations    # 计算TWR/MWR/CAGR/年化收益
      - statistics-fundamentals # 描述性统计/概率分布/假设检验/回归
      - time-value-of-money    # PV/FV/NPV/IRR/贷款还款

  # ── 投资管理层（最丰富：4子域 × 32技能）──
  - id: wealth-management
    name: 财富管理与投资
    version: 1.0.0
    description: 个人和机构投资管理知识——风险/资产/估值/组合/策略
    depends_on: [core]
    skill_count: 32
    has_python: true
    subdomains:
      risk-measurement:        # 1a — 对标 finance_skills
        - historical-risk      # 标准差/Beta/夏普/最大回撤
        - performance-metrics  # Alpha/信息比率/Treynor/Sortino
        - forward-risk         # VaR/CVaR/压力测试/蒙特卡洛
        - volatility-modeling  # GARCH/EGARCH/隐含波动率
      asset-classes:           # 1b — 11资产类别
        - equities             # 股票因子模型/估值比率/指数
        - fixed-income-sovereign # 国债/收益率曲线/久期
        - fixed-income-corporate # 公司债/信用利差/评级
        - fixed-income-structured # MBS/ABS/CDO
        - commodities          # 大宗商品/期货定价
        - real-assets          # REITs/基础设施
        - alternatives         # 对冲基金/PE/VC
        - fund-vehicles        # ETF/共同基金/SMA结构对比
        - currencies-and-fx    # 即期远期/利率平价
        - digital-assets       # 加密货币/代币化
        - china-asset-classes  # 🆕 A股特有:可转债/融资融券/分级基金
      valuation:               # 1c
        - quantitative-valuation # DCF/DDM/FCFF/FCFE
        - qualitative-valuation  # 护城河/五力/ESG
      portfolio-construction:  # 1d
        - diversification      # 相关性/风险平价
        - asset-allocation     # 战略战术/MVO/Black-Litterman
        - bet-sizing           # Kelly/风险预算
        - rebalancing          # 日历/阈值/税收感知
        - investment-policy    # IPS目标约束
      tax-attribution:         # 1e
        - tax-efficiency       # 资产定位/税后对比
        - performance-attribution # Brinson/因子归因
        - tax-loss-harvesting  # 税务亏损收割 🆕 A股专用
      personal-finance:        # 1f
        - debt-management      # 债务雪球vs雪崩
        - emergency-fund       # 应急基金规模
        - savings-goals        # 多目标储蓄
      other:
        - liquidity-management # 现金流匹配
        - finance-psychology   # 行为偏差/前景理论
        - performance-reporting # GIPS合规报告

  # ── 交易运营层 ──
  - id: trading-operations
    name: 交易运营与执行
    version: 1.0.0
    description: 订单生命周期/执行/结算/风控——面向A股市场
    depends_on: [core]
    skill_count: 9
    has_python: false  # 知识指导型
    skills:
      - order-lifecycle       # 订单状态机/A股T+1规则
      - trade-execution       # VWAP/TWAP/流动性分析
      - pre-trade-compliance  # 购买力/持仓限额/涨跌停
      - post-trade-compliance # 异常检测/大额报告
      - settlement-clearing   # T+1结算/中国结算
      - exchange-connectivity # 交易所接口/FIX协议
      - margin-operations     # 融资融券/保证金
      - operational-risk      # 交易中断/对账/BCP
      - counterparty-risk     # 信用敞口/抵押品

  # ── 合规监管层 ──
  - id: compliance
    name: 合规监管（中国版）
    version: 1.0.0
    description: 中国证券市场合规指引——证监会/交易所/中证协/中基协
    depends_on: [core]
    skill_count: 12
    has_python: false
    skills:
      - investment-suitability  # 投资者适当性管理（证监会130号令）
      - know-your-customer      # KYC客户识别
      - anti-money-laundering   # 反洗钱（人民银行3号令）
      - fiduciary-standards     # 信义义务/忠实勤勉
      - fee-disclosure          # 费用披露/隐性费用
      - sales-practices         # 销售实践/推介
      - advertising-compliance  # 营销合规
      - client-disclosures      # 客户披露
      - conflicts-of-interest   # 利益冲突
      - books-and-records       # 账簿记录保留
      - regulatory-reporting    # 监管报送
      - privacy-data-security   # 个人信息保护法

  # ── 数据集成层 ──
  - id: data-integration
    name: 数据集成与治理
    version: 1.0.0
    description: 金融数据基础——参考数据/行情/集成模式/质量
    depends_on: [core]
    skill_count: 4
    has_python: false
    skills:
      - reference-data       # 证券主数据/ISIN映射
      - market-data-feed     # 实时行情/历史数据/Tushare
      - integration-patterns # API/消息队列/ETL管道
      - data-quality         # 数据血缘/异常检测/完整性

# ═══════════════════════════════════════
# 技能分布总结
# ═══════════════════════════════════════
# core:                 3 技能  ✅ Python
# wealth-management:   32 技能  ✅ Python
# trading-operations:   9 技能  ❌ 知识型
# compliance:          12 技能  ❌ 知识型
# client-operations:    8 技能  ❌ 知识型 (计划中)
# data-integration:     4 技能  ❌ 知识型
# ─────────────────────────────────────
# 合计:                68 技能目标  (当前已定义: 60)
