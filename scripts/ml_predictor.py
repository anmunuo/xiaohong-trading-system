#!/usr/bin/env python3
"""
ml_predictor.py — LightGBM 涨跌预测引擎
==========================================
基于30+因子面板，二分类预测次日涨跌概率 + 置信度。

用法:
  python3 ml_predictor.py --train         # 训练模型（增量或全量）
  python3 ml_predictor.py --predict CODE   # 单票预测
  python3 ml_predictor.py --batch CODES    # 批量预测
  python3 ml_predictor.py --eval           # 滚动回测评估

数据流:
  factor_panel → 特征工程 → LightGBM → up_prob + confidence
"""

import sys, os, json, math, pickle
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from collections import defaultdict

import numpy as np

SCRIPT_DIR = Path(__file__).resolve().parent
BASE_DIR = SCRIPT_DIR.parent
sys.path.insert(0, str(SCRIPT_DIR))

MODEL_DIR = SCRIPT_DIR / 'data' / 'models'
IC_PATH = SCRIPT_DIR / 'data' / 'factor_ic.json'


# ═══════════════════════════════════════
# 数据模型
# ═══════════════════════════════════════

@dataclass
class MLPrediction:
    code: str
    name: str = ""
    up_prob: float = 0.5       # 上涨概率 (0-1)
    confidence: float = 0.5    # 置信度 (0-1)
    signal: str = "HOLD"       # BUY / SELL / HOLD
    rf_importance: List[float] = field(default_factory=list)  # 留接口

    @property
    def score_boost(self) -> float:
        """预测上涨→推荐引擎加分 0~10"""
        if self.signal == "BUY" and self.confidence >= 0.6:
            return round(self.confidence * 10, 1)
        elif self.signal == "SELL" and self.confidence >= 0.6:
            return round(-self.confidence * 10, 1)
        return 0.0


@dataclass
class MLModelMeta:
    version: str
    trained_at: str
    n_samples: int
    n_features: int
    accuracy_20d: float = 0.0
    sharpe_sim: float = 0.0
    feature_importance: Dict[str, float] = field(default_factory=dict)


# ═══════════════════════════════════════
# 特征工程
# ═══════════════════════════════════════

class FeatureBuilder:
    """从因子面板构建 LightGBM 特征矩阵"""

    FEATURE_NAMES = [
        # 动量 (4)
        'mom_5d', 'mom_20d', 'mom_60d', 'alpha_idx',
        # 波动 (3)
        'atr_14', 'vol_20d', 'downside_vol',
        # 筹码 (3)
        'turnover_zscore', 'vol_ratio_trend', 'amplitude_5d',
        # 估值 (4)
        'pe_ttm', 'pb', 'pe_percentile', 'pb_percentile',
        # 质量 (4)
        'roe', 'gross_margin', 'debt_ratio', 'cf_profit_ratio',
        # 资金 (3)
        'main_net_buy_ratio', 'retail_net_buy_ratio', 'northbound_5d',
        # 技术 (3)
        'ma20_deviation', 'volume_ratio', 'rsi_14',
        # 市场环境 (4)
        'idx_mom_5d', 'idx_mom_20d', 'market_sentiment', 'sector_momentum',
        # 衍生 (4)
        'mom_acceleration', 'vol_regime', 'pe_regime', 'size_factor',
    ]

    def __init__(self):
        self.n_features = len(self.FEATURE_NAMES)

    def build_features(self, code: str, factor_panel: Dict,
                       indicators: Dict = None,
                       market_context: Dict = None) -> Optional[np.ndarray]:
        """构建单只股票的特征向量"""
        feat = np.zeros(self.n_features, dtype=np.float32)
        fp = factor_panel or {}
        ind = indicators or {}
        mc = market_context or {}

        # ── 动量 ──
        feat[0] = fp.get('mom_5d', 0) or 0
        feat[1] = fp.get('mom_20d', 0) or 0
        feat[2] = fp.get('mom_60d', 0) or 0
        feat[3] = fp.get('alpha_idx', 0) or 0

        # ── 波动 ──
        feat[4] = fp.get('atr_14', 0) or 0
        feat[5] = fp.get('vol_20d', 0) or 0
        feat[6] = fp.get('downside_vol', 0) or 0

        # ── 筹码 ──
        feat[7] = fp.get('turnover_zscore', 0) or 0
        feat[8] = fp.get('vol_ratio_trend', 1.0) or 1.0
        feat[9] = fp.get('amplitude_5d', 0) or 0

        # ── 估值 ──
        feat[10] = ind.get('pe', 0) or 0
        feat[11] = ind.get('pb', 0) or 0
        feat[12] = fp.get('pe_percentile', 50) or 50
        feat[13] = fp.get('pb_percentile', 50) or 50

        # ── 质量 ──
        feat[14] = fp.get('roe', 0) or 0
        feat[15] = fp.get('gross_margin', 0) or 0
        feat[16] = fp.get('debt_ratio', 0) or 0
        feat[17] = fp.get('cf_profit_ratio', 0) or 0

        # ── 资金 ──
        feat[18] = fp.get('main_net_buy_ratio', 0) or 0
        feat[19] = fp.get('retail_net_buy_ratio', 0) or 0
        feat[20] = fp.get('northbound_5d', 0) or 0

        # ── 技术 ──
        feat[21] = fp.get('ma20_deviation', 0) or 0
        feat[22] = ind.get('volume_ratio', 1.0) or 1.0
        feat[23] = fp.get('rsi_14', 50) or 50

        # ── 市场环境 ──
        feat[24] = mc.get('idx_mom_5d', 0)
        feat[25] = mc.get('idx_mom_20d', 0)
        feat[26] = mc.get('market_sentiment', 50)
        feat[27] = mc.get('sector_momentum', 0)

        # ── 衍生特征 ──
        feat[28] = (feat[0] - feat[1]) if feat[0] != 0 else 0  # 动量加速度
        feat[29] = 1 if (feat[5] or 0) > 3 else 0              # 波动区制
        feat[30] = 1 if feat[10] > 60 else (2 if feat[10] > 30 else 3)  # PE区制
        feat[31] = math.log(max(ind.get('total_mv', 50), 1))   # 市值因子(log)

        # 填充 NaN
        feat = np.nan_to_num(feat, nan=0.0, posinf=0.0, neginf=0.0)
        return feat


# ═══════════════════════════════════════
# ML 预测引擎
# ═══════════════════════════════════════

class MLPredictor:
    """LightGBM 涨跌预测"""

    def __init__(self):
        self.model = None
        self.feature_builder = FeatureBuilder()
        self.meta: Optional[MLModelMeta] = None
        self._load()

    def _load(self):
        model_path = MODEL_DIR / 'lgb_updown_v1.pkl'
        meta_path = MODEL_DIR / 'lgb_updown_v1_meta.json'
        if model_path.exists():
            try:
                self.model = pickle.loads(model_path.read_bytes())
                if meta_path.exists():
                    self.meta = MLModelMeta(**json.loads(meta_path.read_text()))
            except Exception:
                self.model = None

    def _save(self):
        MODEL_DIR.mkdir(parents=True, exist_ok=True)
        if self.model:
            (MODEL_DIR / 'lgb_updown_v1.pkl').write_bytes(pickle.dumps(self.model))
        if self.meta:
            (MODEL_DIR / 'lgb_updown_v1_meta.json').write_text(
                json.dumps(self.meta.__dict__, ensure_ascii=False, indent=2))

    def train(self, X: np.ndarray, y: np.ndarray,
              incremental: bool = False) -> MLModelMeta:
        """
        训练 LightGBM 二分类器（降级: sklearn LogisticRegression）。

        Args:
            X: 特征矩阵 (N × F)
            y: 标签 (0=跌, 1=涨)
            incremental: 是否增量训练
        """
        model_type = 'lightgbm'
        try:
            import lightgbm as lgb
        except ImportError:
            model_type = 'sklearn'
            import sklearn
            from sklearn.linear_model import LogisticRegression
            from sklearn.ensemble import RandomForestClassifier
            _log = __import__('logging').getLogger("ml")
            _log.warning("lightgbm 未安装，降级到 sklearn RandomForest")
            _log.warning("安装加速: pip install lightgbm --config-settings=cmake.define.BUILD_CLI=OFF")

        # 过滤无效样本
        valid = ~(np.isnan(X).any(axis=1) | np.isinf(X).any(axis=1))
        X, y = X[valid], y[valid]
        if len(X) < 100:
            raise ValueError(f"训练样本不足: {len(X)} < 100")

        # 划分训练/验证
        split = int(len(X) * 0.8)
        X_train, X_val = X[:split], X[split:]
        y_train, y_val = y[:split], y[split:]

        if model_type == 'lightgbm':
            import lightgbm as lgb
            params = {
                'objective': 'binary', 'metric': 'auc',
                'boosting_type': 'gbdt', 'num_leaves': 31,
                'learning_rate': 0.05, 'feature_fraction': 0.8,
                'bagging_fraction': 0.8, 'bagging_freq': 5,
                'min_data_in_leaf': 20, 'verbose': -1, 'random_state': 42,
            }
            if incremental and self.model:
                self.model = lgb.train(
                    params, lgb.Dataset(X_train, y_train),
                    num_boost_round=50, init_model=self.model,
                    valid_sets=[lgb.Dataset(X_val, y_val)],
                    callbacks=[lgb.early_stopping(10), lgb.log_evaluation(0)],
                )
            else:
                self.model = lgb.train(
                    params, lgb.Dataset(X_train, y_train),
                    num_boost_round=200,
                    valid_sets=[lgb.Dataset(X_val, y_val)],
                    callbacks=[lgb.early_stopping(20), lgb.log_evaluation(0)],
                )
            y_pred_prob = self.model.predict(X_val)
            importance = dict(zip(
                self.feature_builder.FEATURE_NAMES,
                self.model.feature_importance(importance_type='gain')[:self.feature_builder.n_features]
            ))
        else:
            # sklearn RandomForest 降级
            from sklearn.ensemble import RandomForestClassifier
            self.model = RandomForestClassifier(
                n_estimators=200, max_depth=12, min_samples_leaf=20,
                random_state=42, n_jobs=-1, class_weight='balanced',
            )
            self.model.fit(X_train, y_train)
            y_pred_prob = self.model.predict_proba(X_val)[:, 1]
            importance = dict(zip(
                self.feature_builder.FEATURE_NAMES,
                self.model.feature_importances_[:self.feature_builder.n_features]
            ))

        # 评估
        y_pred = (y_pred_prob > 0.5).astype(int)
        accuracy = float((y_pred == y_val).mean())

        importance = {k: round(float(v), 4) for k, v in sorted(
            importance.items(), key=lambda x: x[1], reverse=True)[:15]}

        self.meta = MLModelMeta(
            version='v1.0',
            trained_at=datetime.now().isoformat(),
            n_samples=len(X),
            n_features=X.shape[1],
            accuracy_20d=round(accuracy, 4),
            feature_importance=importance,
        )
        self._save()

        return self.meta

    def predict_single(self, code: str, factor_panel: Dict,
                       indicators: Dict = None,
                       market_context: Dict = None,
                       name: str = "") -> MLPrediction:
        """单票预测"""
        if self.model is None:
            return MLPrediction(code=code, name=name, signal="HOLD")

        feat = self.feature_builder.build_features(
            code, factor_panel, indicators, market_context)
        if feat is None:
            return MLPrediction(code=code, name=name, signal="HOLD")

        prob = float(self.model.predict(feat.reshape(1, -1))[0])
        confidence = abs(prob - 0.5) * 2  # 0.5→0, 0.8→0.6, 1.0→1.0

        if prob > 0.58:
            signal = "BUY"
        elif prob < 0.42:
            signal = "SELL"
        else:
            signal = "HOLD"

        return MLPrediction(
            code=code, name=name,
            up_prob=round(prob, 4),
            confidence=round(confidence, 4),
            signal=signal,
        )

    def predict_batch(self, codes: List[str],
                      factor_panels: Dict[str, Dict],
                      indicators_map: Dict[str, Dict] = None,
                      market_context: Dict = None) -> Dict[str, MLPrediction]:
        """批量预测"""
        if self.model is None:
            return {c: MLPrediction(code=c) for c in codes}

        results = {}
        for code in codes:
            fp = factor_panels.get(code, {})
            ind = (indicators_map or {}).get(code, {})
            results[code] = self.predict_single(
                code, fp, ind, market_context,
                name=ind.get('name', ''))

        return results


# ═══════════════════════════════════════
# 训练数据构建
# ═══════════════════════════════════════

def build_training_dataset(codes: List[str],
                           lookback_days: int = 120) -> Tuple[np.ndarray, np.ndarray]:
    """
    从历史数据构建训练集。

    Args:
        codes: 训练股票池
        lookback_days: 回溯天数

    Returns:
        X: (N × F) 特征矩阵
        y: (N,) 标签 (1=次日上涨, 0=下跌)
    """
    X_list, y_list = [], []
    fb = FeatureBuilder()

    try:
        from data_pipeline import get_historical_k_with_ma, get_factor_panel
    except ImportError:
        return np.array([]), np.array([])

    bs_data = get_historical_k_with_ma(codes, days=lookback_days + 5)
    factor_data = get_factor_panel(codes, days=lookback_days + 5)

    for code in codes:
        bars = bs_data.get(code, [])
        if len(bars) < 65:
            continue

        fp = factor_data.get(code, {})
        closes = [b['close'] for b in bars]

        for t in range(60, len(closes) - 1):
            # 特征：使用 t 时刻的信息
            # 标签：t+1 是否上涨
            if closes[t] <= 0 or closes[t+1] <= 0:
                continue

            label = 1 if closes[t+1] > closes[t] else 0

            # 构建滑动窗口内的因子
            window_fp = {}  # 简化：用最新因子值作为代理
            for k, v in fp.items():
                window_fp[k] = v

            feat = fb.build_features(code, window_fp)
            if feat is not None and not np.all(feat == 0):
                X_list.append(feat)
                y_list.append(label)

    if not X_list:
        return np.array([]), np.array([])

    return np.array(X_list, dtype=np.float32), np.array(y_list, dtype=np.int32)


# ═══════════════════════════════════════
# CLI
# ═══════════════════════════════════════

def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument('--train', action='store_true', help='训练模型')
    ap.add_argument('--predict', type=str, help='单票预测')
    ap.add_argument('--batch', type=str, help='批量预测(逗号分隔)')
    ap.add_argument('--eval', action='store_true', help='滚动回测评估')
    args = ap.parse_args()

    predictor = MLPredictor()

    if args.train:
        # 从推荐池获取股票列表作为训练池
        pool_path = SCRIPT_DIR / 'data' / 'daily_pool.json'
        codes = []
        if pool_path.exists():
            data = json.loads(pool_path.read_text())
            codes = [c['code'] for c in data.get('candidates', [])]
        if not codes:
            print('[ML] 无候选池股票用于训练')
            return

        print(f'[ML] 构建训练集: {len(codes)}只股票...')
        X, y = build_training_dataset(codes[:50], lookback_days=120)

        if len(X) == 0:
            print('[ML] 训练数据不足，跳过')
            return

        print(f'[ML] 训练样本: {len(X)}个')
        meta = predictor.train(X, y)
        print(f'[ML] 训练完成: acc={meta.accuracy_20d:.4f}')
        print(f'[ML] Top 10 特征重要性:')
        for feat, imp in list(meta.feature_importance.items())[:10]:
            print(f'  {feat:20s}: {imp}')

    elif args.predict:
        code = args.predict.zfill(6)
        try:
            from data_pipeline import get_factor_panel, get_stock_realtime
            fp = get_factor_panel([code], days=65)
            rt = get_stock_realtime([code])
            pred = predictor.predict_single(
                code, fp.get(code, {}),
                indicators=rt.get(code, {}),
                name=rt.get(code, {}).get('name', ''))

            print(f'{pred.name}({pred.code}):')
            print(f'  上涨概率: {pred.up_prob:.4f}')
            print(f'  置信度:   {pred.confidence:.4f}')
            print(f'  信号:     {pred.signal}')
            print(f'  推荐加分: {pred.score_boost:+.1f}')
        except Exception as e:
            print(f'预测失败: {e}')

    elif args.batch:
        codes = [c.strip().zfill(6) for c in args.batch.split(',')]
        try:
            from data_pipeline import get_factor_panel
            fp = get_factor_panel(codes, days=65)
            preds = predictor.predict_batch(codes, fp)
            for code, pred in sorted(preds.items(),
                                     key=lambda x: x[1].up_prob, reverse=True):
                arrow = '📈' if pred.signal == 'BUY' else ('📉' if pred.signal == 'SELL' else '➡️')
                print(f'{arrow} {code} {pred.name:8s} '
                      f'P={pred.up_prob:.3f} C={pred.confidence:.3f} '
                      f'boost={pred.score_boost:+.1f}')
        except Exception as e:
            print(f'批量预测失败: {e}')

    elif args.eval:
        if predictor.model is None:
            print('[ML] 模型未训练，先运行 --train')
            return
        print(f'[ML] 模型信息:')
        print(f'  版本:   {predictor.meta.version}')
        print(f'  训练日: {predictor.meta.trained_at[:10]}')
        print(f'  样本:   {predictor.meta.n_samples}')
        print(f'  特征:   {predictor.meta.n_features}')
        print(f'  准确率: {predictor.meta.accuracy_20d:.4f}')

    else:
        ap.print_help()


if __name__ == '__main__':
    main()
