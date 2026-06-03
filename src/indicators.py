"""技术指标计算模块。

所有指标计算集中在这里，不要写到 app.py。
输入统一为带有标准列的 pandas.DataFrame（至少包含 close、volume，
推荐包含 high、low、date）。

提供指标：
- MA5 / MA10 / MA20 / MA60
- RSI14
- MACD / MACD Signal / MACD Histogram
- 近 52 周高点 / 低点
- 近 20 日涨跌幅
- 成交量变化
- 支撑位 / 压力位
"""

from typing import Dict

import numpy as np
import pandas as pd


def _safe_last(series: pd.Series):
    """安全地取序列最后一个非空值，取不到返回 None。"""
    if series is None or len(series) == 0:
        return None
    s = series.dropna()
    if len(s) == 0:
        return None
    value = s.iloc[-1]
    if pd.isna(value):
        return None
    return float(value)


def compute_ma(df: pd.DataFrame, windows=(5, 10, 20, 60)) -> pd.DataFrame:
    """计算多条均线，并把结果写入 df 的新列（MA5、MA10...）。"""
    for w in windows:
        df[f"MA{w}"] = df["close"].rolling(window=w, min_periods=1).mean()
    return df


def compute_rsi(df: pd.DataFrame, period: int = 14) -> pd.DataFrame:
    """计算 RSI 指标，写入 RSI14 列。"""
    delta = df["close"].diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)

    avg_gain = gain.rolling(window=period, min_periods=period).mean()
    avg_loss = loss.rolling(window=period, min_periods=period).mean()

    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    # 当 avg_loss 为 0（持续上涨）时 RSI 视为 100
    rsi = rsi.where(avg_loss != 0, 100.0)
    df[f"RSI{period}"] = rsi
    return df


def compute_macd(
    df: pd.DataFrame,
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
) -> pd.DataFrame:
    """计算 MACD、Signal、Histogram。"""
    ema_fast = df["close"].ewm(span=fast, adjust=False).mean()
    ema_slow = df["close"].ewm(span=slow, adjust=False).mean()
    macd = ema_fast - ema_slow
    macd_signal = macd.ewm(span=signal, adjust=False).mean()
    macd_hist = macd - macd_signal

    df["MACD"] = macd
    df["MACD_Signal"] = macd_signal
    df["MACD_Hist"] = macd_hist
    return df


def compute_all(df: pd.DataFrame) -> pd.DataFrame:
    """在 DataFrame 上计算所有指标列并返回。"""
    if df is None or df.empty:
        return df
    df = df.copy()
    df = compute_ma(df)
    df = compute_rsi(df)
    df = compute_macd(df)
    return df


def _support_resistance(df: pd.DataFrame, lookback: int = 60) -> Dict[str, float]:
    """用近 lookback 日的高低点估算支撑位与压力位。"""
    recent = df.tail(lookback)
    if recent.empty:
        return {"support": None, "resistance": None}

    low_col = "low" if "low" in recent.columns else "close"
    high_col = "high" if "high" in recent.columns else "close"

    support = float(recent[low_col].min())
    resistance = float(recent[high_col].max())
    return {"support": round(support, 3), "resistance": round(resistance, 3)}


def summarize(df: pd.DataFrame) -> Dict[str, object]:
    """计算所有指标并返回一个用于报告/智能体的摘要字典。

    返回的字段尽量都是标量值（最后一个交易日的值），便于直接填入报告。
    """
    empty_summary = {
        "MA5": None,
        "MA10": None,
        "MA20": None,
        "MA60": None,
        "RSI14": None,
        "MACD": None,
        "MACD_Signal": None,
        "MACD_Hist": None,
        "high_52w": None,
        "low_52w": None,
        "change_20d_pct": None,
        "volume_change_pct": None,
        "support": None,
        "resistance": None,
        "trend": "数据不足",
        "data_points": 0,
    }

    if df is None or df.empty:
        return empty_summary

    df = compute_all(df)

    summary = dict(empty_summary)
    summary["data_points"] = int(len(df))
    summary["MA5"] = _round(_safe_last(df.get("MA5")))
    summary["MA10"] = _round(_safe_last(df.get("MA10")))
    summary["MA20"] = _round(_safe_last(df.get("MA20")))
    summary["MA60"] = _round(_safe_last(df.get("MA60")))
    summary["RSI14"] = _round(_safe_last(df.get("RSI14")), 2)
    summary["MACD"] = _round(_safe_last(df.get("MACD")), 4)
    summary["MACD_Signal"] = _round(_safe_last(df.get("MACD_Signal")), 4)
    summary["MACD_Hist"] = _round(_safe_last(df.get("MACD_Hist")), 4)

    # 近 52 周高低点（约 250 个交易日）
    window_52w = df.tail(250)
    high_col = "high" if "high" in df.columns else "close"
    low_col = "low" if "low" in df.columns else "close"
    summary["high_52w"] = _round(float(window_52w[high_col].max()))
    summary["low_52w"] = _round(float(window_52w[low_col].min()))

    # 近 20 日涨跌幅
    if len(df) >= 21:
        start_price = df["close"].iloc[-21]
        end_price = df["close"].iloc[-1]
        if start_price:
            summary["change_20d_pct"] = _round((end_price - start_price) / start_price * 100, 2)
    elif len(df) >= 2:
        start_price = df["close"].iloc[0]
        end_price = df["close"].iloc[-1]
        if start_price:
            summary["change_20d_pct"] = _round((end_price - start_price) / start_price * 100, 2)

    # 成交量变化：最近 5 日均量 vs 前 5 日均量
    if "volume" in df.columns and len(df) >= 10:
        recent_vol = df["volume"].tail(5).mean()
        prev_vol = df["volume"].iloc[-10:-5].mean()
        if prev_vol:
            summary["volume_change_pct"] = _round((recent_vol - prev_vol) / prev_vol * 100, 2)

    # 支撑位 / 压力位
    sr = _support_resistance(df, lookback=60)
    summary["support"] = sr["support"]
    summary["resistance"] = sr["resistance"]

    # 趋势判断（基于均线多头/空头排列）
    summary["trend"] = _judge_trend(summary)

    return summary


def _judge_trend(summary: Dict[str, object]) -> str:
    """根据均线关系给出粗略趋势判断。"""
    ma5 = summary.get("MA5")
    ma20 = summary.get("MA20")
    ma60 = summary.get("MA60")
    if ma5 is None or ma20 is None:
        return "震荡/数据不足"
    if ma60 is not None and ma5 > ma20 > ma60:
        return "多头排列（上升趋势）"
    if ma60 is not None and ma5 < ma20 < ma60:
        return "空头排列（下降趋势）"
    if ma5 > ma20:
        return "偏多（短期均线上穿）"
    if ma5 < ma20:
        return "偏空（短期均线下穿）"
    return "震荡"


def _round(value, ndigits: int = 3):
    """安全四舍五入。"""
    if value is None:
        return None
    try:
        return round(float(value), ndigits)
    except (TypeError, ValueError):
        return None
