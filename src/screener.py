"""短线选股引擎（1–5 天超短线）。

严格按用户规则，用 AKShare 真实数据筛选，不编造：
- 剔除 ST/退市风险/流动性差/近1月解禁(解禁数据缺失时降级跳过并标注)
- 技术：20≤RSI14≤45；MACD 绿柱缩短或刚翻红；现价≥MA5且≥MA10；
        距52周低≥8%；-5%≤近20日涨幅≤+5%
- 资金：近3日主力净流入>0 或 量比>1.3
- 活跃：3%≤换手率≤15%
- 基本面：2026Q1 净利润>0(现金流>0 若可得)；流通市值 50–300 亿
- 价位：入场[MA10,MA5]；止损 min(MA10*0.99, 近5日低)；目标 近20日压力位；
        盈亏比≥1.5 才入选

两阶段：先用 stock_zh_a_spot_em 全市场快照粗筛，再对幸存者拉历史算指标，
避免对全市场逐只拉历史导致卡死。所有网络调用均异常兜底。
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Callable, Dict, List, Optional

import pandas as pd

from . import indicators
from .data_providers.a_share_provider import AShareProvider

# pandas 3.x pyarrow 字符串后端会让 AKShare 的 　 正则清洗报错，关闭推断
try:
    pd.set_option("future.infer_string", False)
except Exception:  # noqa: BLE001
    pass

_provider = AShareProvider()


@dataclass
class ScreenConfig:
    """短线选股阈值（默认 = RSI/超卖短线标准，可在界面逐项调整）。"""

    # —— 技术面 ——
    rsi_min: float = 20.0
    rsi_max: float = 45.0                 # 超卖或中性，不追高
    require_macd_reversal: bool = True    # MACD 绿柱缩短或刚翻红
    require_above_ma5: bool = True        # 现价站上 MA5
    require_above_ma10: bool = True       # 现价站上 MA10
    require_above_ma20: bool = False      # 进阶：也站上 MA20 → 规避空头排列（默认关，建议开）
    dist52_low_min_pct: float = 8.0       # 距52周低 ≥8%（安全垫下限）
    # 新增修正：距52周低 上限。教训——拉普拉斯+70%/淳中+254% 均满足≥8% 却是高位崩跌，
    # 安全垫失真。设上限剔除“远离低点的高位股”，让“低吸”名副其实。
    dist52_low_max_pct: float = 120.0
    chg20_min_pct: float = -5.0           # 近20日涨幅下限（止跌企稳）
    chg20_max_pct: float = 5.0            # 近20日涨幅上限（不追高）

    # —— 资金 / 活跃 ——
    vol_ratio_min: float = 1.3            # 量比 > 1.3
    turnover_min: float = 3.0
    turnover_max: float = 15.0
    min_amount_wan: float = 5000.0        # 日均成交额 > 5000 万（流动性）
    day_chg_max_pct: float = 9.0          # 粗筛排除当日涨停/连板接力

    # —— 基本面 ——
    require_q1_profit_positive: bool = True
    float_cap_min_yi: float = 50.0
    float_cap_max_yi: float = 300.0

    # —— 风控 ——
    min_rr: float = 1.5                   # 盈亏比 ≥1.5 才入选

# 热点题材关键词（用于 name 粗匹配加权；题材最终需人工确认）
HOT_THEME_KEYWORDS = {
    "AI/算力": ["科技", "智能", "算力", "数据", "云", "软件"],
    "光模块/通信": ["光", "通信", "电信", "网络"],
    "半导体": ["芯", "半导体", "微电子", "集成"],
    "机器人": ["机器人", "机电", "自动化", "伺服"],
    "磁材": ["磁", "稀土", "钕"],
    "新能源": ["能源", "电池", "光伏", "储能", "锂"],
}


def _to_float(v, default=None):
    try:
        if v is None or v == "" or (isinstance(v, float) and pd.isna(v)):
            return default
        return float(v)
    except (TypeError, ValueError):
        return default


def _tag_theme(name: str) -> str:
    for theme, kws in HOT_THEME_KEYWORDS.items():
        if any(k in name for k in kws):
            return theme
    return "需人工确认"


# ----------------------------------------------------------------------------
# 大盘环境
# ----------------------------------------------------------------------------
def get_market_env(spot_df: Optional[pd.DataFrame] = None) -> Dict:
    """计算大盘趋势/量能/情绪，并给出建议总仓位。"""
    env = {
        "trend": "未知", "volume": "未知", "breadth": "未知",
        "sentiment": "未知", "suggested_position": "3成（默认保守）",
        "index_close": None, "index_ma20": None, "note": "",
    }

    # 1) 上证指数趋势与量能
    try:
        import akshare as ak

        idx = ak.stock_zh_index_daily(symbol="sh000001")
        if idx is not None and not idx.empty:
            idx = idx.tail(60).copy()
            idx["ma20"] = idx["close"].rolling(20, min_periods=1).mean()
            close = float(idx["close"].iloc[-1])
            ma20 = float(idx["ma20"].iloc[-1])
            env["index_close"] = round(close, 2)
            env["index_ma20"] = round(ma20, 2)
            env["trend"] = "多头（站上MA20）" if close >= ma20 else "空头（跌破MA20）"
            if "volume" in idx.columns and len(idx) >= 10:
                v_recent = idx["volume"].tail(5).mean()
                v_prev = idx["volume"].iloc[-10:-5].mean()
                if v_prev:
                    chg = (v_recent - v_prev) / v_prev * 100
                    env["volume"] = f"{'放量' if chg > 5 else ('缩量' if chg < -5 else '平量')}（环比{chg:+.1f}%）"
    except Exception as exc:  # noqa: BLE001
        env["note"] += f"指数数据获取失败:{exc}; "

    # 2) 涨跌家数（情绪/宽度）
    try:
        if spot_df is not None and not spot_df.empty and "涨跌幅" in spot_df.columns:
            chg = pd.to_numeric(spot_df["涨跌幅"], errors="coerce")
            up = int((chg > 0).sum())
            down = int((chg < 0).sum())
            ratio = up / down if down else float("inf")
            env["breadth"] = f"涨{up}/跌{down}（涨跌比{ratio:.2f}）"
            env["sentiment"] = "偏强" if ratio > 1.2 else ("偏弱" if ratio < 0.8 else "中性")
    except Exception as exc:  # noqa: BLE001
        env["note"] += f"宽度计算失败:{exc}; "

    # 3) 建议仓位
    trend_up = "多头" in env["trend"]
    vol_up = "放量" in env["volume"]
    strong = env["sentiment"] == "偏强"
    if trend_up and (vol_up or strong):
        env["suggested_position"] = "5–7成"
    elif trend_up:
        env["suggested_position"] = "3–5成"
    elif env["sentiment"] == "偏弱":
        env["suggested_position"] = "空仓–3成"
    else:
        env["suggested_position"] = "3成"
    return env


# ----------------------------------------------------------------------------
# 粗筛（全市场快照）
# ----------------------------------------------------------------------------
def _coarse_filter(spot_df: pd.DataFrame, cfg: "ScreenConfig", deep_limit: int) -> pd.DataFrame:
    """基于快照字段做粗筛，返回进入深筛的候选（已限量）。"""
    df = spot_df.copy()

    # 标准化需要的列（东财快照中文列名）
    def col(c):
        return pd.to_numeric(df[c], errors="coerce") if c in df.columns else pd.Series([None] * len(df))

    df["_price"] = col("最新价")
    df["_chg"] = col("涨跌幅")
    df["_turnover"] = col("换手率")
    df["_vol_ratio"] = col("量比")
    df["_amount"] = col("成交额")          # 元
    df["_float_cap"] = col("流通市值")      # 元

    name_col = "名称" if "名称" in df.columns else None
    code_col = "代码" if "代码" in df.columns else None
    if not name_col or not code_col:
        return pd.DataFrame()

    mask = pd.Series(True, index=df.index)
    # 剔除 ST / 退市
    mask &= ~df[name_col].astype(str).str.contains("ST|退", case=False, na=False)
    # 流动性：日均成交额 > 阈值（用当日成交额近似）
    mask &= df["_amount"] > cfg.min_amount_wan * 10000
    # 换手区间
    mask &= (df["_turnover"] >= cfg.turnover_min) & (df["_turnover"] <= cfg.turnover_max)
    # 流通市值区间
    mask &= (df["_float_cap"] >= cfg.float_cap_min_yi * 1e8) & (df["_float_cap"] <= cfg.float_cap_max_yi * 1e8)
    # 资金活跃（量比）—— 主力净流入在深筛阶段补充判断
    mask &= df["_vol_ratio"] > cfg.vol_ratio_min
    # 近20日涨幅在深筛算，这里先用当日涨幅排除明显涨停/连板
    mask &= df["_chg"] < cfg.day_chg_max_pct

    out = df[mask].copy()
    # 排序：量比优先（活跃但不极端），取前 deep_limit 进深筛
    out = out.sort_values("_vol_ratio", ascending=False).head(deep_limit)
    return out


# ----------------------------------------------------------------------------
# Q1 业绩（一次性获取全市场，避免逐只）
# ----------------------------------------------------------------------------
def _fetch_q1_profit(date: str = "20260331") -> Dict[str, dict]:
    """获取 2026Q1 业绩报表，返回 code -> {net_profit, ...}。失败返回空。"""
    try:
        import akshare as ak

        df = ak.stock_yjbb_em(date=date)
        if df is None or df.empty:
            return {}
        out = {}
        for _, r in df.iterrows():
            code = str(r.get("股票代码") or r.get("代码") or "").strip()
            if not code:
                continue
            out[code] = {
                "net_profit": _to_float(r.get("净利润")),
                "revenue": _to_float(r.get("营业总收入") or r.get("营业收入")),
                "cfps": _to_float(r.get("每股经营现金流量") or r.get("每股经营性现金流")),
            }
        return out
    except Exception as exc:  # noqa: BLE001
        print(f"[screener] Q1业绩获取失败，基本面将标注需核验: {exc}")
        return {}


# ----------------------------------------------------------------------------
# 深筛 + 价位计算
# ----------------------------------------------------------------------------
def _deep_check(code: str, name: str, spot_price: float, vol_ratio: float,
                turnover: float, float_cap: float,
                q1: Dict[str, dict], start: str, end: str,
                cfg: "ScreenConfig") -> Optional[dict]:
    """对单只票拉历史算指标并应用硬性条件，通过则返回候选 dict。"""
    df = _provider.get_history(code, start, end, "daily", "qfq")
    if df is None or df.empty or len(df) < 30:
        return None

    d = indicators.compute_all(df)
    summ = indicators.summarize(df)
    price = spot_price or float(d["close"].iloc[-1])

    ma5 = summ.get("MA5"); ma10 = summ.get("MA10"); ma20 = summ.get("MA20")
    rsi = summ.get("RSI14"); chg20 = summ.get("change_20d_pct")
    low52 = summ.get("low_52w")
    if None in (ma5, ma10, rsi, chg20, low52):
        return None

    # 技术硬性条件（全部来自 cfg，可调）
    if not (cfg.rsi_min <= rsi <= cfg.rsi_max):
        return None
    if cfg.require_above_ma5 and price < ma5:
        return None
    if cfg.require_above_ma10 and price < ma10:
        return None
    if cfg.require_above_ma20 and (ma20 is None or price < ma20):
        return None
    # 距52周低：下限(安全垫) + 上限(剔除高位崩跌的假安全垫)
    if low52 <= 0:
        return None
    dist = (price - low52) / low52 * 100
    if dist < cfg.dist52_low_min_pct or dist > cfg.dist52_low_max_pct:
        return None
    if not (cfg.chg20_min_pct <= chg20 <= cfg.chg20_max_pct):
        return None

    # MACD：绿柱缩短 或 刚翻红
    hist = d["MACD_Hist"].dropna()
    if len(hist) < 2:
        return None
    h1, h0 = float(hist.iloc[-1]), float(hist.iloc[-2])
    just_red = h1 > 0 and h0 <= 0
    green_shrink = h1 < 0 and h1 > h0
    if cfg.require_macd_reversal and not (just_red or green_shrink):
        return None

    # 基本面：流通市值（粗筛已过，复核）+ Q1 净利润>0
    fund = q1.get(code, {})
    net_profit = fund.get("net_profit")
    cfps = fund.get("cfps")
    if cfg.require_q1_profit_positive and net_profit is not None and net_profit <= 0:
        return None
    if cfps is not None and cfps < 0:
        return None
    fund_status = "Q1净利>0" if (net_profit and net_profit > 0) else "Q1业绩需核验"
    if cfps is not None:
        fund_status += "、现金流>0" if cfps >= 0 else ""

    # 价位
    entry_low = round(min(ma5, ma10) * 0.995, 2)
    entry_high = round(max(ma5, ma10), 2)
    entry_mid = round((entry_low + entry_high) / 2, 2)
    low5 = float(d["low"].tail(5).min()) if "low" in d.columns else entry_low * 0.97
    stop = round(min(ma10 * 0.99, low5), 2)
    if stop >= entry_mid:
        stop = round(entry_mid * 0.97, 2)
    # 第一目标：近20日压力位
    high20 = float(d["high"].tail(20).max()) if "high" in d.columns else price * 1.08
    target = round(max(high20, entry_mid * 1.05), 2)

    risk = entry_mid - stop
    reward = target - entry_mid
    if risk <= 0:
        return None
    rr = round(reward / risk, 2)
    if rr < cfg.min_rr:
        return None

    # 仓位 & 加仓
    if rr >= 2.5:
        first_pos = "2成"
    else:
        first_pos = "1成"
    add_cond = f"放量站稳 {entry_high} 上方且量比>1.3，加 1 成"

    theme = _tag_theme(name)
    score = rr * (1.3 if theme != "需人工确认" else 1.0) * (vol_ratio or 1)

    macd_state = "刚翻红" if just_red else "绿柱缩短"
    logic = (
        f"RSI{rsi:.0f}（{'超卖' if rsi < 30 else '中性'}不追高）｜MACD {macd_state}首次反转｜"
        f"站上MA5/MA10短期转强｜距52周低{(price-low52)/low52*100:.0f}%有安全垫；"
        f"量比{vol_ratio:.1f}活跃、换手{turnover:.1f}%；题材：{theme}"
    )

    return {
        "code": code, "name": name, "price": round(price, 2),
        "rsi": round(rsi, 1), "ma5": round(ma5, 2), "ma10": round(ma10, 2),
        "ma20": round(ma20, 2) if ma20 else None,
        "macd_state": macd_state, "chg20": round(chg20, 2),
        "dist_52w_low_pct": round((price - low52) / low52 * 100, 1),
        "vol_ratio": round(vol_ratio, 2) if vol_ratio else None,
        "turnover": round(turnover, 2) if turnover else None,
        "float_cap_yi": round(float_cap / 1e8, 1) if float_cap else None,
        "theme": theme, "fund_status": fund_status,
        "entry_low": entry_low, "entry_high": entry_high,
        "stop": stop, "target": target, "rr": rr,
        "first_position": first_pos, "add_condition": add_cond,
        "logic": logic, "score": round(score, 2),
    }


# ----------------------------------------------------------------------------
# 主入口
# ----------------------------------------------------------------------------
def run_screen(deep_limit: int = 40, top_n: int = 5,
               cfg: Optional["ScreenConfig"] = None,
               progress_callback: Optional[Callable[[str, float], None]] = None) -> Dict:
    """执行完整选股流程，返回 {market_env, candidates, meta}。"""
    cfg = cfg or ScreenConfig()

    def report(msg, frac):
        if progress_callback:
            progress_callback(msg, frac)

    meta = {"data_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "universe": 0, "coarse": 0, "deep_checked": 0, "errors": [],
            "config": cfg.__dict__.copy()}

    # 1) 全市场快照（带重试，弱网下提升成功率）
    report("拉取全市场快照…", 0.05)
    spot_df = pd.DataFrame()
    import time as _time
    for attempt in range(3):
        try:
            import akshare as ak

            spot_df = ak.stock_zh_a_spot_em()
            if spot_df is not None and not spot_df.empty:
                meta["universe"] = len(spot_df)
                break
        except Exception as exc:  # noqa: BLE001
            meta["errors"].append(f"快照获取失败(第{attempt+1}次):{exc}")
            _time.sleep(1.5)

    # 2) 大盘环境
    report("计算大盘环境…", 0.12)
    market_env = get_market_env(spot_df)

    if spot_df is None or spot_df.empty:
        return {"market_env": market_env, "candidates": [], "meta": meta}

    # 3) 粗筛
    report("粗筛（市值/换手/量比/流动性）…", 0.2)
    coarse = _coarse_filter(spot_df, cfg, deep_limit)
    meta["coarse"] = len(coarse)

    # 4) Q1 业绩（一次性）
    report("获取 2026Q1 业绩…", 0.28)
    q1 = _fetch_q1_profit("20260331")

    # 5) 深筛
    end = datetime.now().strftime("%Y%m%d")
    start = (datetime.now() - timedelta(days=420)).strftime("%Y%m%d")
    candidates: List[dict] = []
    n = max(len(coarse), 1)
    for i, (_, row) in enumerate(coarse.iterrows()):
        code = str(row["代码"]).strip()
        name = str(row["名称"]).strip()
        report(f"深筛 {i+1}/{len(coarse)}：{name}", 0.3 + 0.65 * (i / n))
        meta["deep_checked"] += 1
        try:
            c = _deep_check(
                code, name,
                _to_float(row.get("_price")), _to_float(row.get("_vol_ratio")),
                _to_float(row.get("_turnover")), _to_float(row.get("_float_cap")),
                q1, start, end, cfg,
            )
            if c:
                candidates.append(c)
        except Exception as exc:  # noqa: BLE001
            meta["errors"].append(f"{code} 深筛异常:{exc}")

    candidates.sort(key=lambda x: x["score"], reverse=True)
    report("完成", 1.0)
    return {"market_env": market_env, "candidates": candidates[:top_n], "meta": meta}
