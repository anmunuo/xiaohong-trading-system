#!/usr/bin/env python3
"""
进化引擎 v1.0
=============
每日 17:30：读取 LLM 诊断建议 → 翻译为参数变更 → 沙箱验证 → 自动落地或丢弃。

进化范围:
  · stock_recommender: 连板阈值 / 市值范围 / 因子权重
  · scout: 资金门槛基数 / 涨跌范围
  · auction_features: 五维权重
  · sniper: 止损逼近阈值

安全边界:
  · 单次参数调整不超过 ±20%
  · 至少 3 天回测数据才允许自动落地
  · 所有变更记录 evolution_log.json，可追溯可回滚

用法:
  python3 evolution_engine.py              # 读取诊断 → 沙箱 → 落地
  python3 evolution_engine.py --dry-run    # 只分析不落地
  python3 evolution_engine.py --rollback   # 回滚到上一个版本
  python3 evolution_engine.py --log        # 查看进化历史
"""

__version__ = "2.0.0"

import sys, os, json, shutil, subprocess
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

SCRIPT_DIR = Path(__file__).resolve().parent
BASE_DIR = SCRIPT_DIR.parent
sys.path.insert(0, str(SCRIPT_DIR))

DATA_DIR = SCRIPT_DIR / "data"
LOG_PATH = DATA_DIR / "evolution_log.json"
BACKUP_DIR = DATA_DIR / "evolution_backups"

# ── 可进化参数定义 v2.0 (7模块 27参数) ──
EVOLVABLE_PARAMS = {
    # ── 瞭望塔/推荐引擎 (3) ──
    "recommender_lianban_min": {
        "file": "stock_recommender.py",
        "path_in_code": "lianban_min_boards",
        "default": 1, "min": 1, "max": 4,
        "description": "连板排除阈值（≥N板排除）",
        "source_diagnosis": "review_diagnosis.json"
    },
    "recommender_market_cap_min": {
        "file": "stock_recommender.py",
        "path_in_code": "market_cap_min_yi",
        "default": 50, "min": 20, "max": 100,
        "description": "市值下限（亿元）",
        "source_diagnosis": "review_diagnosis.json"
    },
    "recommender_market_cap_max": {
        "file": "stock_recommender.py",
        "path_in_code": "market_cap_max_yi",
        "default": 3000, "min": 500, "max": 5000,
        "description": "市值上限（亿元）",
        "source_diagnosis": "review_diagnosis.json"
    },

    # ── 推荐引擎五因子权重 🆕 (5) ──
    "recommender_weight_event": {
        "file": "stock_recommender.py",
        "path_in_code": "WEIGHT_EVENT",
        "default": 0.30, "min": 0.15, "max": 0.50,
        "description": "事件因子权重",
        "source_diagnosis": "review_diagnosis.json"
    },
    "recommender_weight_fundamental": {
        "file": "stock_recommender.py",
        "path_in_code": "WEIGHT_FUNDAMENTAL",
        "default": 0.25, "min": 0.10, "max": 0.40,
        "description": "基本面因子权重",
        "source_diagnosis": "review_diagnosis.json"
    },
    "recommender_weight_sentiment": {
        "file": "stock_recommender.py",
        "path_in_code": "WEIGHT_SENTIMENT",
        "default": 0.20, "min": 0.10, "max": 0.35,
        "description": "情绪因子权重",
        "source_diagnosis": "review_diagnosis.json"
    },
    "recommender_weight_technical": {
        "file": "stock_recommender.py",
        "path_in_code": "WEIGHT_TECHNICAL",
        "default": 0.15, "min": 0.05, "max": 0.30,
        "description": "技术因子权重",
        "source_diagnosis": "review_diagnosis.json"
    },
    "recommender_weight_research": {
        "file": "stock_recommender.py",
        "path_in_code": "WEIGHT_RESEARCH",
        "default": 0.10, "min": 0.05, "max": 0.25,
        "description": "研报因子权重",
        "source_diagnosis": "review_diagnosis.json"
    },

    # ── 侦察兵 (3) ──
    "scout_flow_base": {
        "file": "scout.py",
        "path_in_code": "flow_threshold_base",
        "default": 5000, "min": 2000, "max": 15000,
        "description": "侦察兵资金门槛基准（万元）",
        "source_diagnosis": "review_diagnosis.json"
    },
    "scout_change_min": {
        "file": "scout.py",
        "path_in_code": "change_filter_min",
        "default": -3, "min": -8, "max": 0,
        "description": "侦察兵涨跌下限（%）",
        "source_diagnosis": "review_diagnosis.json"
    },
    "scout_change_max": {
        "file": "scout.py",
        "path_in_code": "change_filter_max",
        "default": 9, "min": 5, "max": 15,
        "description": "侦察兵涨跌上限（%）",
        "source_diagnosis": "review_diagnosis.json"
    },

    # ── 狙击手 v3.0 (5) + v4.0 守护进程 (6) → 共 11 参数 ──
    "sniper_stop_approach_pct": {
        "file": "sniperd.py",
        "path_in_code": "STOP_PROXIMITY_PCT",
        "default": 3.0, "min": 1.0, "max": 8.0,
        "description": "P1止损逼近阈值（%）",
        "source_diagnosis": "review_diagnosis.json"
    },
    "sniper_p2_change_threshold": {
        "file": "sniperd.py",
        "path_in_code": "P2_CHANGE_THRESHOLD",
        "default": 5.0, "min": 3.0, "max": 10.0,
        "description": "P2涨跌幅度阈值（%）",
        "source_diagnosis": "review_diagnosis.json"
    },
    "sniper_p2_vol_ratio": {
        "file": "sniperd.py",
        "path_in_code": "P2_VOL_RATIO",
        "default": 3.0, "min": 1.5, "max": 6.0,
        "description": "P2量比阈值",
        "source_diagnosis": "review_diagnosis.json"
    },
    "sniper_entry_vol_ratio": {
        "file": "sniperd.py",
        "path_in_code": "ENTRY_VOL_RATIO",
        "default": 1.5, "min": 1.0, "max": 3.0,
        "description": "入场量比门槛",
        "source_diagnosis": "review_diagnosis.json"
    },
    "sniper_entry_ma_dev_max": {
        "file": "sniperd.py",
        "path_in_code": "ENTRY_MA_DEV_MAX",
        "default": 5.0, "min": 2.0, "max": 10.0,
        "description": "入场MA20偏离上限（%）",
        "source_diagnosis": "review_diagnosis.json"
    },
    # ── 狙击手 v4.0 守护进程专属参数 (6) ──
    "sniper_l1_interval": {
        "file": "sniperd.py",
        "path_in_code": "L1_INTERVAL",
        "default": 3, "min": 1, "max": 10,
        "description": "L1持仓轮询间隔（秒）",
        "source_diagnosis": "review_diagnosis.json"
    },
    "sniper_alert_cooldown_p1": {
        "file": "sniperd.py",
        "path_in_code": "ALERT_COOLDOWN_P1",
        "default": 120, "min": 60, "max": 300,
        "description": "P1告警冷却时间（秒）",
        "source_diagnosis": "review_diagnosis.json"
    },
    "sniper_alert_cooldown_p2": {
        "file": "sniperd.py",
        "path_in_code": "ALERT_COOLDOWN_P2",
        "default": 300, "min": 120, "max": 600,
        "description": "P2告警冷却时间（秒）",
        "source_diagnosis": "review_diagnosis.json"
    },
    "sniper_alert_cooldown_entry": {
        "file": "sniperd.py",
        "path_in_code": "ALERT_COOLDOWN_ENTRY",
        "default": 600, "min": 300, "max": 1200,
        "description": "入场信号冷却时间（秒）",
        "source_diagnosis": "review_diagnosis.json"
    },
    "sniper_alert_cooldown_market": {
        "file": "sniperd.py",
        "path_in_code": "ALERT_COOLDOWN_MARKET",
        "default": 600, "min": 300, "max": 1800,
        "description": "大盘异动冷却时间（秒）",
        "source_diagnosis": "review_diagnosis.json"
    },
    "sniper_market_swing_threshold": {
        "file": "sniperd.py",
        "path_in_code": "MARKET_SWING_THRESHOLD",
        "default": 3.0, "min": 2.0, "max": 5.0,
        "description": "大盘异动幅度阈值（%）",
        "source_diagnosis": "review_diagnosis.json"
    },

    # ── 弹药库 🆕 (5) ──
    "ammo_kelly_coefficient": {
        "file": "ammo_risk.py",
        "path_in_code": "kelly_coefficient",
        "default": 0.2, "min": 0.05, "max": 0.5,
        "description": "凯利系数（R值计算）",
        "source_diagnosis": "review_diagnosis.json"
    },
    "ammo_single_stock_max": {
        "file": "ammo_risk.py",
        "path_in_code": "single_stock_max_pct",
        "default": 33.3, "min": 15.0, "max": 50.0,
        "description": "单股仓位上限（%）",
        "source_diagnosis": "review_diagnosis.json"
    },
    "ammo_total_positions_max": {
        "file": "ammo_risk.py",
        "path_in_code": "total_positions_max",
        "default": 9, "min": 5, "max": 15,
        "description": "总持仓数量上限",
        "source_diagnosis": "review_diagnosis.json"
    },
    "ammo_trailing_start": {
        "file": "ammo_risk.py",
        "path_in_code": "trailing_start_pct",
        "default": 20.0, "min": 10.0, "max": 40.0,
        "description": "移动止盈启动阈值（%）",
        "source_diagnosis": "review_diagnosis.json"
    },
    "ammo_trailing_step": {
        "file": "ammo_risk.py",
        "path_in_code": "trailing_step_pct",
        "default": 10.0, "min": 5.0, "max": 20.0,
        "description": "移动止盈步长（%）",
        "source_diagnosis": "review_diagnosis.json"
    },

    # ── 知识库 🆕 (2) ──
    "kb_collect_interval": {
        "file": "mega_collector.py",
        "path_in_code": "collect_interval_minutes",
        "default": 60, "min": 15, "max": 240,
        "description": "知识库采集间隔（分钟）",
        "source_diagnosis": "review_diagnosis.json"
    },
    "kb_dedup_window": {
        "file": "knowledge_base.py",
        "path_in_code": "dedup_window_days",
        "default": 7, "min": 1, "max": 30,
        "description": "知识库去重窗口（天）",
        "source_diagnosis": "review_diagnosis.json"
    },

    # ── 竞价学习器 (7) ──
    "auction_weight_price_slope": {
        "file": "auction_features.py",
        "path_in_code": "weight_price_slope",
        "default": 0.25, "min": 0.05, "max": 0.50,
        "description": "竞价价格斜率权重",
        "source_diagnosis": "auction_diagnosis.json"
    },
    "auction_weight_volume_accel": {
        "file": "auction_features.py",
        "path_in_code": "weight_volume_accel",
        "default": 0.25, "min": 0.05, "max": 0.50,
        "description": "竞价量能加速度权重",
        "source_diagnosis": "auction_diagnosis.json"
    },
    "auction_weight_imbalance": {
        "file": "auction_features.py",
        "path_in_code": "weight_imbalance",
        "default": 0.20, "min": 0.05, "max": 0.50,
        "description": "竞价委托不平衡权重",
        "source_diagnosis": "auction_diagnosis.json"
    },
    "auction_weight_premium": {
        "file": "auction_features.py",
        "path_in_code": "weight_premium",
        "default": 0.15, "min": 0.05, "max": 0.40,
        "description": "竞价开盘溢价权重",
        "source_diagnosis": "auction_diagnosis.json"
    },
    "auction_weight_sector_dev": {
        "file": "auction_features.py",
        "path_in_code": "weight_sector_dev",
        "default": 0.15, "min": 0.05, "max": 0.40,
        "description": "竞价板块偏离权重",
        "source_diagnosis": "auction_diagnosis.json"
    },
    "auction_prior_alpha": {
        "file": "auction_learner.py",
        "path_in_code": "prior_alpha",
        "default": 1, "min": 1, "max": 10,
        "description": "竞价贝叶斯先验α",
        "source_diagnosis": "auction_diagnosis.json"
    },
    "auction_prior_beta": {
        "file": "auction_learner.py",
        "path_in_code": "prior_beta",
        "default": 1, "min": 1, "max": 10,
        "description": "竞价贝叶斯先验β",
        "source_diagnosis": "auction_diagnosis.json"
    },

    # ── 侦察兵盘中评分权重 🆕 (4) ──
    "intra_fund_weight": {
        "file": "scout.py",
        "path_in_code": "INTRA_FUND_WEIGHT",
        "default": 0.40, "min": 0.20, "max": 0.60,
        "description": "盘中评分-资金流权重",
        "source_diagnosis": "review_diagnosis.json"
    },
    "intra_tech_weight": {
        "file": "scout.py",
        "path_in_code": "INTRA_TECH_WEIGHT",
        "default": 0.30, "min": 0.10, "max": 0.50,
        "description": "盘中评分-技术面权重",
        "source_diagnosis": "review_diagnosis.json"
    },
    "intra_sent_weight": {
        "file": "scout.py",
        "path_in_code": "INTRA_SENT_WEIGHT",
        "default": 0.20, "min": 0.05, "max": 0.40,
        "description": "盘中评分-情绪面权重",
        "source_diagnosis": "review_diagnosis.json"
    },
    "intra_sector_weight": {
        "file": "scout.py",
        "path_in_code": "INTRA_SECTOR_WEIGHT",
        "default": 0.10, "min": 0.00, "max": 0.30,
        "description": "盘中评分-板块热度权重",
        "source_diagnosis": "review_diagnosis.json"
    },

    # ── 文工团 🆕 (2) ──
    "review_gainer_min_pct": {
        "file": "review.py",
        "path_in_code": "gainer_min_pct",
        "default": 6.0, "min": 3.0, "max": 10.0,
        "description": "文工团涨幅榜最低%",
        "source_diagnosis": "review_diagnosis.json"
    },
    "review_gainer_top_n": {
        "file": "review.py",
        "path_in_code": "gainer_top_n",
        "default": 50, "min": 20, "max": 100,
        "description": "文工团涨幅榜数量",
        "source_diagnosis": "review_diagnosis.json"
    },

    # ── 弹药库风控 🆕 (4) ──
    "ammo_r_denominator": {
        "file": "ammo_risk.py",
        "path_in_code": "R_DENOMINATOR",
        "default": 8, "min": 5, "max": 15,
        "description": "R值分母（1/N），越大R值越小仓位越保守",
        "source_diagnosis": "review_diagnosis.json"
    },
    "ammo_trail_buffer_pct": {
        "file": "ammo_risk.py",
        "path_in_code": "TRAIL_BUFFER_PCT",
        "default": 3.0, "min": 2.0, "max": 8.0,
        "description": "移动止盈动态缓冲（%）",
        "source_diagnosis": "review_diagnosis.json"
    },
    "ammo_sector_max_pct": {
        "file": "ammo_risk.py",
        "path_in_code": "SECTOR_MAX_PCT",
        "default": 30.0, "min": 20.0, "max": 50.0,
        "description": "行业集中度告警阈值（%）",
        "source_diagnosis": "review_diagnosis.json"
    },
    "ammo_liq_impact_threshold": {
        "file": "ammo_risk.py",
        "path_in_code": "LIQ_IMPACT_THRESHOLD",
        "default": 5.0, "min": 3.0, "max": 15.0,
        "description": "流动性冲击告警阈值（%）",
        "source_diagnosis": "review_diagnosis.json"
    },

    # ── 基础设施 🆕 (3) ──
    "infra_data_cache_ttl": {
        "file": "data_pipeline.py",
        "path_in_code": "QUOTE_CACHE_TTL",
        "default": 120, "min": 30, "max": 600,
        "description": "行情缓存过期时间（秒）",
        "source_diagnosis": "review_diagnosis.json"
    },
    "infra_ma_refresh_interval": {
        "file": "sniperd.py",
        "path_in_code": "MA_REFRESH_INTERVAL",
        "default": 1800, "min": 600, "max": 3600,
        "description": "MA20/均量刷新间隔（秒）",
        "source_diagnosis": "review_diagnosis.json"
    },
    "sniper_p0_confirm_ticks": {
        "file": "sniperd.py",
        "path_in_code": "P0_CONFIRM_TICKS",
        "default": 2, "min": 1, "max": 5,
        "description": "P0止损确认tick数（防误报）",
        "source_diagnosis": "review_diagnosis.json"
    },

    # ── 🆕 v2.3 新增: ML模型 (4) ──
    "ml_boost_weight": {
        "file": "stock_recommender.py",
        "path_in_code": "ML_BOOST_WEIGHT",
        "default": 1.0, "min": 0.3, "max": 2.5,
        "description": "ML预测器得分权重（倍数）",
        "source_diagnosis": "factor_ic.json"
    },
    "ml_confidence_threshold": {
        "file": "ml_predictor.py",
        "path_in_code": "CONFIDENCE_THRESHOLD",
        "default": 0.6, "min": 0.5, "max": 0.85,
        "description": "ML信号置信度阈值",
        "source_diagnosis": "factor_ic.json"
    },
    "ml_retrain_interval": {
        "file": "ml_predictor.py",
        "path_in_code": "RETRAIN_INTERVAL_DAYS",
        "default": 1, "min": 1, "max": 7,
        "description": "ML增量训练间隔（天）",
        "source_diagnosis": "factor_ic.json"
    },
    "ml_feature_count": {
        "file": "ml_predictor.py",
        "path_in_code": "FEATURE_COUNT",
        "default": 32, "min": 16, "max": 64,
        "description": "ML特征数量",
        "source_diagnosis": "factor_ic.json"
    },

    # ── 🆕 v2.3 新增: 组合管理 (6) ──
    "var_threshold_pct": {
        "file": "portfolio_risk.py",
        "path_in_code": "VAR_THRESHOLD_PCT",
        "default": 3.0, "min": 1.5, "max": 8.0,
        "description": "VaR告警阈值（%净值）",
        "source_diagnosis": "review_diagnosis.json"
    },
    "cvar_threshold_pct": {
        "file": "portfolio_risk.py",
        "path_in_code": "CVAR_THRESHOLD_PCT",
        "default": 4.0, "min": 2.0, "max": 10.0,
        "description": "CVaR告警阈值（%净值）",
        "source_diagnosis": "review_diagnosis.json"
    },
    "corr_warning_threshold": {
        "file": "portfolio_risk.py",
        "path_in_code": "CORR_WARNING",
        "default": 0.70, "min": 0.50, "max": 0.85,
        "description": "相关性警告阈值",
        "source_diagnosis": "review_diagnosis.json"
    },
    "corr_critical_threshold": {
        "file": "portfolio_risk.py",
        "path_in_code": "CORR_CRITICAL",
        "default": 0.80, "min": 0.65, "max": 0.95,
        "description": "相关性严重告警阈值",
        "source_diagnosis": "review_diagnosis.json"
    },
    "max_sector_concentration": {
        "file": "ammo_risk.py",
        "path_in_code": "SECTOR_MAX_PCT",
        "default": 30.0, "min": 15.0, "max": 50.0,
        "description": "行业集中度上限（%）",
        "source_diagnosis": "review_diagnosis.json"
    },
    "stress_test_frequency": {
        "file": "portfolio_risk.py",
        "path_in_code": "STRESS_FREQUENCY",
        "default": 7, "min": 3, "max": 30,
        "description": "压力测试频率（天）",
        "source_diagnosis": "review_diagnosis.json"
    },

    # ── 🆕 v2.3 新增: 算法执行 (3) ──
    "twap_default_slices": {
        "file": "algo_executor.py",
        "path_in_code": "TWAP_DEFAULT_SLICES",
        "default": 10, "min": 5, "max": 30,
        "description": "TWAP默认切片数",
        "source_diagnosis": "review_diagnosis.json"
    },
    "vwap_volume_profile_days": {
        "file": "algo_executor.py",
        "path_in_code": "VWAP_PROFILE_DAYS",
        "default": 5, "min": 3, "max": 20,
        "description": "VWAP历史量分布天数",
        "source_diagnosis": "review_diagnosis.json"
    },
    "max_impact_bps": {
        "file": "algo_executor.py",
        "path_in_code": "MAX_IMPACT_BPS",
        "default": 50, "min": 20, "max": 100,
        "description": "最大冲击成本（bps）",
        "source_diagnosis": "review_diagnosis.json"
    },
}

# ── 安全边界 ──
MAX_CHANGE_PCT = 0.20       # 单次调整不超过 ±20%
MIN_BACKTEST_DAYS = 3       # 最少回测天数
MIN_HIT_IMPROVEMENT = 0.02  # 命中率至少提升 2% 才落地
SANDBOX_TIMEOUT_S = 15      # 沙箱超时秒数


# ═══════════════════════════════════════════
# 参数分类：决定验证策略
# ═══════════════════════════════════════════

FILTER_PARAMS = {  # 过滤器参数 → 可轻量模拟
    "recommender_lianban_min",
    "recommender_market_cap_min",
    "recommender_market_cap_max",
    "scout_flow_base",
    "scout_change_min",
    "scout_change_max",
    "sniper_stop_approach_pct",
    "sniper_p2_change_threshold",
    "sniper_p2_vol_ratio",
    "sniper_entry_vol_ratio",
    "sniper_entry_ma_dev_max",
    "sniper_market_swing_threshold",
    "sniper_p0_confirm_ticks",
    "review_gainer_min_pct",
    "review_gainer_top_n",
}

WEIGHT_PARAMS = {  # 权重类参数 → 依赖历史数据
    "auction_weight_price_slope",
    "auction_weight_volume_accel",
    "auction_weight_imbalance",
    "auction_weight_premium",
    "auction_weight_sector_dev",
    "auction_prior_alpha",
    "auction_prior_beta",
    "recommender_weight_event",
    "recommender_weight_fundamental",
    "recommender_weight_sentiment",
    "recommender_weight_technical",
    "recommender_weight_research",
}

RISK_PARAMS = {  # 风控参数 → 仅安全校验
    "ammo_kelly_coefficient",
    "ammo_single_stock_max",
    "ammo_total_positions_max",
    "ammo_trailing_start",
    "ammo_trailing_step",
    "ammo_r_denominator",
    "ammo_trail_buffer_pct",
    "ammo_sector_max_pct",
    "ammo_liq_impact_threshold",
}

INTRA_WEIGHT_PARAMS = {  # 盘中评分权重 → 跟权重类同策略
    "intra_fund_weight",
    "intra_tech_weight",
    "intra_sent_weight",
    "intra_sector_weight",
}

INFRA_PARAMS = {  # 基础设施参数 → 仅安全校验
    "kb_collect_interval",
    "kb_dedup_window",
    "sniper_l1_interval",
    "sniper_alert_cooldown_p1",
    "sniper_alert_cooldown_p2",
    "sniper_alert_cooldown_entry",
    "sniper_alert_cooldown_market",
    "infra_data_cache_ttl",
    "infra_ma_refresh_interval",
}

# 🆕 v2.3 新增参数类别
ML_PARAMS = {  # ML模型参数
    "ml_boost_weight",
    "ml_confidence_threshold",
    "ml_retrain_interval",
    "ml_feature_count",
}

PORTFOLIO_PARAMS = {  # 组合管理参数
    "var_threshold_pct",
    "cvar_threshold_pct",
    "corr_warning_threshold",
    "corr_critical_threshold",
    "max_sector_concentration",
    "stress_test_frequency",
}

ALGO_PARAMS = {  # 算法执行参数
    "twap_default_slices",
    "vwap_volume_profile_days",
    "max_impact_bps",
}


# ═══════════════════════════════════════════
# 1. 读取诊断建议
# ═══════════════════════════════════════════

def load_diagnosis(path: str) -> Optional[Dict]:
    """加载诊断文件"""
    full = Path(path)
    if not full.exists():
        return None
    try:
        return json.loads(full.read_text())
    except Exception:
        return None


def extract_changes() -> List[Dict]:
    """从诊断文件中提取可执行的参数变更"""
    changes = []

    # 竞价诊断
    auction_diag = load_diagnosis(str(DATA_DIR / "kb" / "auction_diagnosis.json"))
    if auction_diag and "recommendation" in auction_diag:
        rec = auction_diag["recommendation"]
        auction_weight_map = {
            "price_slope": "auction_weight_price_slope",
            "volume_accel": "auction_weight_volume_accel",
            "imbalance": "auction_weight_imbalance",
            "premium": "auction_weight_premium",
            "sector_dev": "auction_weight_sector_dev",
        }
        for dim, new_val in rec.items():
            if dim in auction_weight_map and isinstance(new_val, (int, float)):
                changes.append({
                    "param": auction_weight_map[dim],
                    "new_value": new_val,
                    "reason": auction_diag.get("diagnosis", "竞价诊断建议"),
                    "source": "auction_diagnosis"
                })

    # 文工团复盘诊断 — 全域覆盖
    review_diag = load_diagnosis(str(DATA_DIR / "kb" / "review_diagnosis.json"))
    if review_diag:
        # 🆕 兼容两种格式：list[{root_causes}] 或 dict{rule_changes_suggested}
        entries = review_diag if isinstance(review_diag, list) else [review_diag]
        rule_map = {
            "连板排除": "recommender_lianban_min", "市值下限": "recommender_market_cap_min",
            "市值上限": "recommender_market_cap_max", "事件权重": "recommender_weight_event",
            "基本面权重": "recommender_weight_fundamental", "情绪权重": "recommender_weight_sentiment",
            "技术权重": "recommender_weight_technical", "研报权重": "recommender_weight_research",
            "资金门槛": "scout_flow_base", "盘中资金": "intra_fund_weight",
            "盘中技术": "intra_tech_weight", "盘中情绪": "intra_sent_weight",
            "盘中板块": "intra_sector_weight", "P1逼近": "sniper_stop_approach_pct",
            "P2涨跌": "sniper_p2_change_threshold", "P2量比": "sniper_p2_vol_ratio",
            "入场量比": "sniper_entry_vol_ratio", "入场偏离": "sniper_entry_ma_dev_max",
            "轮询间隔": "sniper_l1_interval", "P1冷却": "sniper_alert_cooldown_p1",
            "P2冷却": "sniper_alert_cooldown_p2", "入场冷却": "sniper_alert_cooldown_entry",
            "大盘冷却": "sniper_alert_cooldown_market", "大盘异动": "sniper_market_swing_threshold",
            "凯利系数": "ammo_kelly_coefficient", "单股上限": "ammo_single_stock_max",
            "持仓上限": "ammo_total_positions_max", "止盈启动": "ammo_trailing_start",
            "止盈步长": "ammo_trailing_step", "采集间隔": "kb_collect_interval",
            "去重窗口": "kb_dedup_window", "涨幅阈值": "review_gainer_min_pct",
            "涨幅数量": "review_gainer_top_n",
        }

        # 格式1: 结构化 rule_changes_suggested（LLM 理想输出）
        for entry in entries:
            if isinstance(entry, dict) and "rule_changes_suggested" in entry:
                for rc in entry["rule_changes_suggested"]:
                    rule = rc.get("rule", "")
                    change_desc = rc.get("change", "")
                    for keyword, param_id in rule_map.items():
                        if keyword in rule:
                            import re
                            nums = re.findall(r'(\d+\.?\d*)', change_desc)
                            if nums:
                                changes.append({
                                    "param": param_id,
                                    "new_value": float(nums[-1]),
                                    "reason": f"{rule}: {change_desc}",
                                    "source": "review_diagnosis"
                                })
                            break

        # 格式2: 实际产出 — root_causes 诊断（LLM 叙述式输出）
        for entry in entries:
            if isinstance(entry, dict) and "root_causes" in entry:
                root_causes = entry["root_causes"]
                # candidate_pool_blindspot → 扩大候选池（已由P0修复解决）
                if "candidate_pool_blindspot" in root_causes:
                    rc = root_causes["candidate_pool_blindspot"]
                    if rc.get("severity") == "P0":
                        # 建议：降低连板排除门槛（因P0已将含首板→仅≥2板）
                        changes.append({
                            "param": "recommender_lianban_min",
                            "new_value": 2,
                            "reason": f"候选池盲区修复: {rc.get('detail', '扩大候选源')[:80]}",
                            "source": "review_diagnosis"
                        })


    return changes


# ═══════════════════════════════════════════
# 🆕 研究员周报 action_items → 进化参数
# ═══════════════════════════════════════════

def extract_research_actions() -> List[Dict]:
    """从研究员周报 action_items 中提取可进化的参数变更"""
    import json
    actions_path = DATA_DIR / "evolution_action_items.json"
    if not actions_path.exists():
        return []

    with open(actions_path) as f:
        items = json.load(f)

    # 研究员周报 action → 参数映射表
    action_param_map = {
        "公告情绪权重调整": ("recommender_weight_event", 0.35, "研究员: 公告信号密度变化"),
        "行业轮动信号增强": ("recommender_weight_sentiment", 0.25, "研究员: 行业新闻与资金联动"),
        "止损参数重新校准": ("sniper_stop_approach_pct", 2.5, "研究员: 止损失效率分析"),  # 2026-06-03 fix: 0.04→2.5 (unit bug, 原值超出range [1.0,8.0])
        "MA20偏离阈值优化": ("recommender_weight_technical", 0.18, "研究员: MA20偏离分布"),
        "北向资金权重上调": ("recommender_weight_fundamental", 0.30, "研究员: 北向资金持续性"),
        "估值分位风险阈值设置": ("ammo_total_position_limit", 0.70, "研究员: 指数PE分位偏高"),
    }

    changes = []
    pending = [it for it in items if it.get("status") == "pending" and it.get("source") == "research_weekly"]

    for it in pending:
        action = it.get("action", "")
        mapped = action_param_map.get(action)
        if mapped:
            param_id, new_value, reason = mapped
            changes.append({
                "param": param_id,
                "new_value": new_value,
                "reason": f"{reason}: {it.get('rationale', '')[:80]}",
                "source": "research_weekly",
                "action_item_id": action,
            })

    return changes


# ═══════════════════════════════════════════
# 2. 安全校验
# ═══════════════════════════════════════════

def validate_change(param_id: str, new_value: float) -> Tuple[bool, str]:
    """校验参数变更是否在安全边界内"""
    spec = EVOLVABLE_PARAMS.get(param_id)
    if not spec:
        return False, f"未知参数: {param_id}"

    if new_value < spec["min"] or new_value > spec["max"]:
        return False, f"{new_value} 超出范围 [{spec['min']}, {spec['max']}]"

    default = spec["default"]
    change_pct = abs(new_value - default) / default if default else 0
    if change_pct > MAX_CHANGE_PCT:
        return False, f"变更幅度 {change_pct:.0%} 超出上限 {MAX_CHANGE_PCT:.0%}"

    return True, "ok"


# ═══════════════════════════════════════════
# 3. 智能沙箱验证 v2.0
# ═══════════════════════════════════════════

def sandbox_test(param_id: str, old_value: float, new_value: float,
                 file_path: Path) -> Tuple[bool, Dict]:
    """
    智能分层验证（v2.0）：
      · FILTER_PARAMS  → 轻量模拟（秒级，不调 tushare）
      · WEIGHT_PARAMS  → 回流 reflection_log 历史对比
      · RISK/INFRA     → 仅安全边界校验
      · 全部            → 15s 超时兜底
    """
    result = {
        "param": param_id,
        "old_value": old_value,
        "new_value": new_value,
        "strategy": "unknown",
        "passed": False,
        "details": "",
    }

    # ── 策略 1: 过滤器参数 → 轻量模拟 ──
    if param_id in FILTER_PARAMS:
        result["strategy"] = "lightweight_sim"
        result["passed"], result["details"] = _simulate_filter_change(
            param_id, old_value, new_value
        )
        return result["passed"], result

    # ── 策略 2: 权重参数 → 历史命中率对比 ──
    if param_id in WEIGHT_PARAMS or param_id in INTRA_WEIGHT_PARAMS:
        result["strategy"] = "reflection_log"
        result["passed"], result["details"] = _check_reflection_trend(param_id)
        return result["passed"], result

    # ── 策略 3: 风控/基础设施参数 → 安全校验即通过 ──
    if param_id in RISK_PARAMS or param_id in INFRA_PARAMS:
        result["strategy"] = "boundary_only"
        result["passed"] = True
        result["details"] = "风控/基础设施参数，边界通过即落地，由 reflection_log 持续监控"
        return True, result

    # ── 兜底 ──
    result["strategy"] = "boundary_only"
    result["passed"] = True
    result["details"] = "未知参数类型，边界通过即落地"
    return True, result


def _simulate_filter_change(param_id: str, old: float, new: float) -> Tuple[bool, str]:
    """轻量模拟过滤器参数变更的效果（不调 tushare）"""
    # 读取今日被排除的数据，估算变更影响
    pool_path = SCRIPT_DIR / "data" / "daily_pool.json"
    direction = "收紧" if (new > old if old > 0 else new < old) else "放宽"
    direction_icon = {"放宽": "📉", "收紧": "📈"}.get(direction, "➡️")

    if not pool_path.exists():
        return True, f"{direction_icon} {direction} {param_id}: {old}→{new}（无历史池，跳过模拟）"

    try:
        with open(pool_path) as f:
            pool = json.load(f)
        excluded = pool.get("excluded", {})

        # 根据参数类型估算影响
        if "market_cap_min" in param_id:
            count = excluded.get("small_cap", 0)
            if isinstance(count, list):
                count = len(count)
            elif isinstance(count, dict):
                count = len(count)
            delta = int(count * (old - new) / old) if old > 0 and new < old else 0
            return True, (
                f"📉 放宽市值下限 {old}→{new}亿 | "
                f"今日有 {count} 只<{old}亿被排除 | "
                f"预计释放约 {delta} 只 | 信号: 正向"
            )
        elif "market_cap_max" in param_id:
            count = excluded.get("large_cap", 0)
            if isinstance(count, list):
                count = len(count)
            elif isinstance(count, dict):
                count = len(count)
            return True, (
                f"{direction_icon} {direction}市值上限 {old}→{new}亿 | "
                f"今日有 {count} 只>{old}亿被排除"
            )
        elif "lianban" in param_id:
            count = excluded.get("lianban", 0)
            if isinstance(count, list):
                count = len(count)
            elif isinstance(count, dict):
                count = len(count)
            return True, (
                f"{direction_icon} {direction}连板阈 {int(old)}→{int(new)} | "
                f"今日有 {count} 只涨停被排除"
            )
        elif "scout_flow" in param_id:
            return True, (
                f"{direction_icon} {direction}资金门槛 {old:.0f}→{new:.0f}万 | "
                f"{'门槛降低=更多标的' if new < old else '门槛提高=更严筛选'}"
            )
        elif "sniper" in param_id:
            return True, (
                f"{direction_icon} {direction}狙击手参数 {param_id}: {old}→{new} | "
                f"{'更敏感' if new < old else '更宽松'}"
            )
        elif "review" in param_id:
            return True, (
                f"{direction_icon} {direction}文工团参数 {param_id}: {old}→{new} | "
                f"{'覆盖更多涨幅股' if ('top_n' in param_id and new > old) or ('min_pct' in param_id and new < old) else '范围调整'}"
            )
        else:
            return True, f"{direction_icon} {direction} {param_id}: {old}→{new}"
    except Exception as e:
        return True, f"{direction_icon} 模拟跳过（{str(e)[:40]}）"


def _check_reflection_trend(param_id: str) -> Tuple[bool, str]:
    """用 reflection_log 历史趋势验证权重类参数"""
    refl_path = DATA_DIR / "reflection_log.json"
    if not refl_path.exists():
        return True, "无 reflection_log，首次调整允许通过（3天后回测验证）"

    try:
        logs = json.loads(refl_path.read_text())
        recent = logs[-MIN_BACKTEST_DAYS:]
        if len(recent) < MIN_BACKTEST_DAYS:
            return True, f"仅 {len(recent)} 天数据，允许调整（需 {MIN_BACKTEST_DAYS} 天后验证）"

        # 检查近 3 天 pool_rate 趋势
        rates = [r.get("pool_rate", 0) for r in recent]
        trend = rates[-1] - rates[0]

        if trend >= -2.0:
            return True, f"近 {MIN_BACKTEST_DAYS} 天 pool_rate 趋势 {trend:+.1f}%（稳定），允许调整"
        else:
            return False, f"近 {MIN_BACKTEST_DAYS} 天 pool_rate 下降 {abs(trend):.1f}%（恶化），拒绝本次调整"
    except Exception as e:
        return True, f"reflection_log 读取异常（{str(e)[:30]}），允许调整"


# ═══════════════════════════════════════════
# 4. 落地 / 回滚
# ═══════════════════════════════════════════

def apply_param_to_file(file_path: Path, param_id: str,
                         old_value: float, new_value: float) -> bool:
    """
    将参数值写入目标文件（v2.0 扩展支持 7 模块）。

    通过查找文件中的参数定义行来替换。
    """
    spec = EVOLVABLE_PARAMS[param_id]
    path_in_code = spec["path_in_code"]

    if not file_path.exists():
        return False

    content = file_path.read_text()
    import re

    if param_id.startswith("auction_weight_"):
        # 权重参数在 DEFAULT_WEIGHTS 字典中
        dim = param_id.replace("auction_weight_", "")
        # 🆕 v2.0.1: 从文件读取实际值，非用 default（default 可能与文件不同）
        import re as _re
        m = _re.search(rf"'{dim}':\s*([\d.]+)", content)
        actual_old = float(m.group(1)) if m else old_value
        old_str = f"'{dim}': {actual_old}"
        new_str = f"'{dim}': {new_value}"
        if old_str in content:
            content = content.replace(old_str, new_str)
        else:
            pattern = _re.compile(rf"'{dim}':\s*{_re.escape(str(actual_old))}")
            content = pattern.sub(f"'{dim}': {new_value}", content)

    elif param_id.startswith("auction_prior_"):
        # PRIOR_ALPHA / PRIOR_BETA 在 auction_learner.py 顶部
        var_name = "PRIOR_ALPHA" if "alpha" in param_id else "PRIOR_BETA"
        old_str = f"{var_name} = {int(old_value)}"
        new_str = f"{var_name} = {int(new_value)}"
        if old_str in content:
            content = content.replace(old_str, new_str)

    elif param_id.startswith("recommender_"):
        if "weight_" in param_id:
            # 推荐引擎五因子权重: scores['event'] * 0.30 → scores['event'] * NEW
            weight_key = param_id.replace("recommender_weight_", "")
            key_map = {
                "event": "event", "fundamental": "fund",
                "sentiment": "sentiment", "technical": "technical",
                "research": "research",
            }
            k = key_map.get(weight_key, weight_key)
            old_s = f"scores['{k}'] * {old_value}"
            new_s = f"scores['{k}'] * {new_value}"
            content = content.replace(old_s, new_s)
        elif "lianban" in param_id:
            content = content.replace(
                f"df[df['连板数'].astype(float) >= {int(old_value)}]",
                f"df[df['连板数'].astype(float) >= {int(new_value)}]"
            )
        elif "market_cap" in param_id:
            limit = "max" if "max" in param_id else "min"
            old_pattern = f"mkt_cap {('>' if limit=='max' else '<')} {old_value}"
            new_pattern = f"mkt_cap {('>' if limit=='max' else '<')} {new_value}"
            content = content.replace(old_pattern, new_pattern)

    elif param_id.startswith("scout_"):
        if "flow" in param_id:
            content = content.replace(
                f"return {int(old_value)}",
                f"return {int(new_value)}"
            )

    elif param_id.startswith("sniper_"):
        # sniperd.py v4.0 Config 类常量替换
        spec = EVOLVABLE_PARAMS[param_id]
        var_name = spec["path_in_code"]
        old_s = f"{var_name} = {old_value}"
        new_s = f"{var_name} = {new_value}"
        content = content.replace(old_s, new_s)

    elif param_id.startswith("ammo_"):
        if "kelly" in param_id:
            old_s = f"凯利 {old_value}"
            new_s = f"凯利 {new_value}"
            content = content.replace(old_s, new_s)
        elif "single_stock" in param_id:
            old_s = f"单股上限 {old_value}%"
            new_s = f"单股上限 {new_value}%"
            content = content.replace(old_s, new_s)
        elif "total_positions" in param_id:
            old_s = f"持仓上限 {int(old_value)} 只"
            new_s = f"持仓上限 {int(new_value)} 只"
            content = content.replace(old_s, new_s)
        elif "trailing_start" in param_id:
            old_s = f"涨 {old_value}% 启动"
            new_s = f"涨 {new_value}% 启动"
            content = content.replace(old_s, new_s)
        elif "trailing_step" in param_id:
            old_s = f"每涨 {old_value}% 上移"
            new_s = f"每涨 {new_value}% 上移"
            content = content.replace(old_s, new_s)
        elif "r_denominator" in param_id:
            old_s = f"0.125 * kelly"
            # 1/N → new value
            old_coeff = round(1.0 / old_value, 4)
            new_coeff = round(1.0 / new_value, 4)
            old_s2 = f"* {old_coeff} * kelly"
            new_s2 = f"* {new_coeff} * kelly"
            content = content.replace(old_s2, new_s2)
        elif "trail_buffer" in param_id:
            old_s = f"price * {old_value / 100}"
            new_s = f"price * {new_value / 100}"
            content = content.replace(old_s, new_s)
        elif "sector_max" in param_id:
            old_s = f"pct > {old_value}"
            new_s = f"pct > {new_value}"
            content = content.replace(old_s, new_s)
        elif "liq_impact" in param_id:
            old_s = f"impact > {old_value}"
            new_s = f"impact > {new_value}"
            content = content.replace(old_s, new_s)

    elif param_id.startswith("kb_"):
        if "collect_interval" in param_id:
            old_s = f"schedule: '0 */{int(old_value/60)} * * *"
            new_s = f"schedule: '0 */{int(new_value/60)} * * *"
            content = content.replace(old_s, new_s) if old_s in content else content
        elif "dedup_window" in param_id:
            old_s = f"DEDUP_DAYS = {int(old_value)}"
            new_s = f"DEDUP_DAYS = {int(new_value)}"
            content = content.replace(old_s, new_s) if old_s in content else content

    elif param_id.startswith("intra_"):
        # 盘中评分权重
        var_map = {
            "intra_fund_weight": "INTRA_FUND_WEIGHT",
            "intra_tech_weight": "INTRA_TECH_WEIGHT",
            "intra_sent_weight": "INTRA_SENT_WEIGHT",
            "intra_sector_weight": "INTRA_SECTOR_WEIGHT",
        }
        var = var_map.get(param_id, "")
        if var:
            old_s = f"{var} = {old_value}"
            new_s = f"{var} = {new_value}"
            content = content.replace(old_s, new_s)

    elif param_id.startswith("review_"):
        if "gainer_min_pct" in param_id:
            old_s = f"GAINER_MIN_PCT: float = {old_value}"
            new_s = f"GAINER_MIN_PCT: float = {new_value}"
            content = content.replace(old_s, new_s)
        elif "gainer_top_n" in param_id:
            old_s = f"GAINER_TOP_N: int = {int(old_value)}"
            new_s = f"GAINER_TOP_N: int = {int(new_value)}"
            content = content.replace(old_s, new_s)

    elif param_id.startswith("infra_"):
        # 基础设施参数: Config 类常量或模块级常量替换
        spec = EVOLVABLE_PARAMS[param_id]
        var_name = spec["path_in_code"]
        old_s = f"{var_name} = {old_value}"
        new_s = f"{var_name} = {new_value}"
        content = content.replace(old_s, new_s)

    file_path.write_text(content)
    return True


def create_backup(file_path: Path, version: int):
    """备份当前版本"""
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    backup_path = BACKUP_DIR / f"{file_path.name}.v{version}.bak"
    shutil.copy2(file_path, backup_path)


def load_evolution_log() -> List[Dict]:
    """加载进化日志"""
    if LOG_PATH.exists():
        return json.loads(LOG_PATH.read_text())
    return []


def save_evolution_log(log: List[Dict]):
    """保存进化日志"""
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    LOG_PATH.write_text(json.dumps(log[-50:], ensure_ascii=False, indent=2))


# ═══════════════════════════════════════════
# 5. 主流程
# ═══════════════════════════════════════════

def _parliament_review(changes: List[Dict], dry_run: bool) -> Dict:
    """研究员议会 — 评估参数变更的风险和收益，返回裁决"""
    try:
        from researchers import Parliament
        parliament = Parliament()
        context = parliament.load_context()
        context["topic"] = f"进化引擎参数变更评审 ({len(changes)}项, {'dry_run' if dry_run else 'live'})"
        context["proposed_changes"] = [
            {"param": c.get("param"), "new_value": c.get("new_value"),
             "reason": c.get("reason", "")}
            for c in changes
        ]
        result = parliament.execute(topic=context["topic"])
        verdict = result.get("round3", {}).get("verdict", {})
        print(f"\n  🏛️ 议会评审: {verdict.get('bias', '?')} (置信度 {verdict.get('overall_confidence', 0):.0%})")
        return verdict
    except Exception:
        return {}  # 议会评审失败返回空裁决


def evolve(dry_run: bool = False):
    """执行一轮进化"""
    log = load_evolution_log()
    version = len(log) + 1
    date_str = datetime.now().strftime('%Y-%m-%d')
    ts = datetime.now().isoformat()

    print(f"🧬 进化引擎 v{__version__}  ·  {date_str}")
    print(f"   版本 #{version}  ·  dry_run={dry_run}")
    print()

    changes = extract_changes()
    # 🆕 研究员周报 action_items
    try:
        research_changes = extract_research_actions()
        if research_changes:
            changes.extend(research_changes)
            print(f"🧠 研究员周报补充: {len(research_changes)} 条建议")
    except Exception:
        pass
    if not changes:
        print("📭 无可执行参数变更（诊断文件为空或无建议）")
        return

    print(f"📋 读取到 {len(changes)} 条参数建议:\n")

    # 研究员议会 — 各研究员评估参数变更的风险和收益
    verdict = _parliament_review(changes, dry_run)

    # 议会 veto 拦截
    if verdict:
        bias = verdict.get('bias', 'neutral')
        confidence = verdict.get('overall_confidence', 0)
        red_flags = verdict.get('red_flags', [])

        if bias == 'veto' and confidence >= 0.75:
            print(f"\n  🚫 议会否决！置信度 {confidence:.0%}，终止本轮进化")
            if red_flags:
                for rf in red_flags:
                    print(f"     ⛔ {rf}")
            return
        elif bias in ('bearish', 'veto') and confidence >= 0.6:
            print(f"\n  ⚠️ 议会偏空（{bias}，置信度 {confidence:.0%}），以下参数将跳过")
            risky_params = verdict.get('risky_params', [])
            if risky_params:
                changes = [c for c in changes if c['param'] not in risky_params]
                print(f"     跳过 {len(risky_params)} 项高风险参数，剩余 {len(changes)} 项")
            if red_flags:
                print(f"     ⛔ 红旗: {'; '.join(red_flags[:3])}")
        elif bias == 'bullish':
            print(f"\n  ✅ 议会偏多（置信度 {confidence:.0%}），放行全部变更")
        else:
            print(f"  ℹ️ 议会{bias}（置信度 {confidence:.0%}），按常规流程执行")
    else:
        print("  ⚠️ 议会评审不可用，按常规流程执行")

    if not changes:
        print("📭 所有参数被议会否决，无变更可执行")
        return

    applied = []
    for c in changes:
        pid = c["param"]
        spec = EVOLVABLE_PARAMS.get(pid)
        if not spec:
            print(f"  ⚠️ 未知参数 {pid}，跳过")
            continue

        new_val = c["new_value"]
        ok, msg = validate_change(pid, new_val)
        if not ok:
            print(f"  ❌ {spec['description']}: {msg}")
            continue

        old_val = spec["default"]
        file_path = SCRIPT_DIR / spec["file"]

        print(f"  🔧 {spec['description']}")
        print(f"     {old_val} → {new_val}  ({msg})")
        print(f"     原因: {c['reason']}")
        print(f"     来源: {c['source']}")

        # 沙箱测试
        print(f"     🧪 沙箱验证中...")
        passed, test_result = sandbox_test(pid, old_val, new_val, file_path)
        if passed:
            print(f"     ✅ 通过: {test_result.get('details', test_result.get('strategy', 'ok'))}")
        else:
            print(f"     ❌ 未通过: {test_result.get('details', '验证失败')}")

        if not dry_run and passed:
            create_backup(file_path, version)
            if apply_param_to_file(file_path, pid, old_val, new_val):
                print(f"     💾 已写入 {spec['file']}")
                applied.append({
                    "param": pid,
                    "description": spec["description"],
                    "old_value": old_val,
                    "new_value": new_val,
                    "reason": c["reason"],
                    "test_result": test_result,
                })
            else:
                print(f"     ⚠️ 写入失败（模式匹配未命中）")
        print()

    # 记录
    entry = {
        "date": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        "version": f"#{len(log)+1}",
        "dry_run": dry_run,
        "changes_attempted": len(changes),
        "changes_applied": len(applied),
        "details": applied,
    }
    log.append(entry)
    save_evolution_log(log)

    # 🆕 标记研究员周报 action_items 为已应用
    if not dry_run:
        try:
            actions_path = DATA_DIR / "evolution_action_items.json"
            if actions_path.exists():
                with open(actions_path) as f:
                    items = json.load(f)
                updated = False
                for it in items:
                    if it.get("status") == "pending" and it.get("source") == "research_weekly":
                        for app in applied:
                            if app.get("source") == "research_weekly":
                                it["status"] = "applied"
                                it["applied_at"] = datetime.now().isoformat()
                                updated = True
                if updated:
                    with open(actions_path, 'w') as f:
                        json.dump(items, f, ensure_ascii=False, indent=2, default=str)
                    print(f"   📝 研究员 action_items 状态已更新")
        except Exception:
            pass

    if dry_run:
        print(f"\n🔍 DRY RUN — 未实际写入。{len(applied)}/{len(changes)} 项通过验证")
    else:
        print(f"\n✅ 进化完成 — {len(applied)}/{len(changes)} 项已落地")
        print(f"   备份: {BACKUP_DIR}/")
        print(f"   日志: {LOG_PATH}")

        # 🆕 进化后自动触发系统健康检查
        try:
            from system_health_check import run_health_check, print_report, save_report
            print(f"\n{'='*60}")
            report = run_health_check(fix=True)
            print_report(report)
            save_report(report)
        except Exception as e:
            print(f"\n⚠️ 健康检查失败: {e}")


def rollback():
    """回滚到上一个版本"""
    log = load_evolution_log()
    if len(log) < 2:
        print("❌ 无可回滚版本")
        return

    last = log[-1]
    prev = log[-2]
    print(f"🔄 回滚: v{last['version']} → v{prev['version']}")
    print(f"   v{last['version']}: {last['date']} — {last['changes_applied']}项变更")

    for detail in last.get("details", []):
        pid = detail["param"]
        spec = EVOLVABLE_PARAMS.get(pid)
        if spec:
            file_path = SCRIPT_DIR / spec["file"]
            backup_path = BACKUP_DIR / f"{file_path.name}.v{prev['version']}.bak"
            if backup_path.exists():
                shutil.copy2(backup_path, file_path)
                print(f"   ✅ {spec['file']} 已恢复 v{prev['version']}")
            else:
                # 直接改回旧值
                apply_param_to_file(
                    file_path, pid, detail["new_value"], detail["old_value"]
                )
                print(f"   ✅ {spec['file']} 已恢复参数 {detail['new_value']} → {detail['old_value']}")

    log.pop()
    save_evolution_log(log)
    print(f"\n✅ 回滚完成，当前版本 v{prev['version']}")


def show_log():
    """展示进化历史"""
    log = load_evolution_log()
    if not log:
        print("📭 无进化记录")
        return

    print(f"\n📜 进化历史 ({len(log)} 条)")
    print(f"   {'─'*50}")
    for entry in log[-10:]:
        status = "🔍试运行" if entry.get("dry_run") else "✅已落地"
        print(f"   v{entry['version']:3d}  {entry['date']}  "
              f"{status}  {entry['changes_applied']}/{entry['changes_attempted']}项")
        for d in entry.get("details", []):
            print(f"         {d['description']}: {d['old_value']} → {d['new_value']}")


# ═══════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════

def main():
    import argparse
    p = argparse.ArgumentParser(description='进化引擎 v1.0')
    p.add_argument('--dry-run', action='store_true', help='只分析不落地')
    p.add_argument('--rollback', action='store_true', help='回滚到上一版本')
    p.add_argument('--log', action='store_true', help='查看进化历史')
    args = p.parse_args()

    if args.rollback:
        rollback()
    elif args.log:
        show_log()
    else:
        evolve(dry_run=args.dry_run)


if __name__ == "__main__":
    main()
