"""信号回测：用历史数据验证各信号的真实期望，砍掉没用的规则。

方法（无前视）：对候选池逐只拉历史日线，逐根 bar t 仅用 ≤t 的数据算信号，
模拟 t 收盘进场、止损=破MA5(MA5×0.99)、持有至多 hold 日（先到止损则止损出，
否则 t+hold 收盘出），记录每笔收益，按信号类型汇总：
样本数 / 胜率 / 平均 / 中位 / 盈亏比 / 止损率。

口径说明：信号每日可重复触发（趋势股会产生大量重叠样本），故这是"条件化前瞻收益"
的统计度量，不是不重叠的独立交易；但各信号的平均/胜率对比仍能说明哪类有边际。
不构成投资建议。
"""

from concurrent.futures import ThreadPoolExecutor
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd

from . import daily_watch, indicators, sector_screener

try:
    pd.set_option("future.infer_string", False)
except Exception:  # noqa: BLE001
    pass


def _universe() -> Dict[str, str]:
    uni: Dict[str, str] = {}
    for _tier, d in daily_watch.WATCHLIST.items():
        for c, n in d.items():
            uni[c] = n
    for _sec, d in sector_screener.POOLS.items():
        for c, n in d.items():
            uni.setdefault(c, n)
    return uni


def _signal(close, ma5, ma10, rsi, h1, volr) -> str:
    """与 daily_watch 同口径的信号判定（单根 bar）。"""
    if close < ma5 * 0.99:
        return "🔴破位预警"
    if rsi <= 30:
        return "🔵超卖埋伏"
    above5 = close >= ma5
    if above5 and ma5 > ma10 and volr > 1.3 and h1 > 0 and rsi >= 45:
        return "✅放量突破多头"
    if above5 and close >= ma10 and volr > 1.3:
        return "⭐放量站MA10(奖牌口径)"
    if above5 and abs(close / ma5 - 1) <= 0.025 and volr < 1.0:
        return "🟢回踩低吸缩量"
    if above5:
        return "⚪站上MA5观望"
    return "⚪跌破MA5观望"


def backtest_stock(code: str, hold: int = 5, exit_mode: str = "fixed",
                   max_hold: int = 20) -> List[Tuple[str, float, bool]]:
    """exit_mode：
    - 'fixed'：进场后持有 hold 日，期间破MA5(low≤MA5×0.99)则止损出，否则 t+hold 收盘出。
    - 'trail'：让赢家跑——每日收盘跌破当日 MA5×0.99 才清，最多持有 max_hold 日。
    破位/跌破MA5类信号(进场已在止损下方)用"无止损纯前瞻 hold 日收益"，避免止损价高于进场价的假数据。
    """
    d = daily_watch._fetch(code, retries=2)
    if d is None or len(d) < 120:
        return []
    d = indicators.compute_all(d).reset_index(drop=True)
    closes = d["close"].to_numpy(dtype=float)
    lows = d["low"].to_numpy(dtype=float)
    vols = d["volume"].to_numpy(dtype=float)
    ma5 = d["MA5"].to_numpy(dtype=float)
    ma10 = d["MA10"].to_numpy(dtype=float)
    rsi = d["RSI14"].to_numpy(dtype=float)
    hist = d["MACD_Hist"].to_numpy(dtype=float)
    n = len(d)
    horizon = max_hold if exit_mode == "trail" else hold
    out: List[Tuple[str, float, bool]] = []
    for t in range(60, n - horizon - 1):
        if np.isnan(ma10[t]) or np.isnan(rsi[t]) or closes[t] <= 0:
            continue
        prev5 = vols[t - 5:t].mean()
        volr = vols[t] / prev5 if prev5 > 0 else 0.0
        sig = _signal(closes[t], ma5[t], ma10[t], rsi[t], hist[t], volr)
        entry = closes[t]
        stop = ma5[t] * 0.99
        # 进场已在止损下方(破位/超卖跌破MA5)：止损逻辑不成立 → 记纯前瞻 hold 日收益(验证该不该碰)
        if entry <= stop:
            ret = (closes[t + hold] / entry - 1) * 100
            out.append((sig, ret, False))
            continue
        ret = None
        hit_stop = False
        if exit_mode == "trail":
            for k in range(1, max_hold + 1):
                if closes[t + k] < ma5[t + k] * 0.99:  # 收盘跌破MA5才清，让赢家跑
                    ret = (closes[t + k] / entry - 1) * 100
                    hit_stop = closes[t + k] < entry
                    break
            if ret is None:
                ret = (closes[t + max_hold] / entry - 1) * 100
        else:
            for k in range(1, hold + 1):
                if lows[t + k] <= stop:
                    ret = (stop / entry - 1) * 100
                    hit_stop = True
                    break
            if ret is None:
                ret = (closes[t + hold] / entry - 1) * 100
        out.append((sig, ret, hit_stop))
    return out


def _agg(trades: List[Tuple[str, float, bool]]) -> Dict:
    agg: Dict[str, Dict] = {}
    for sig, ret, hit in trades:
        a = agg.setdefault(sig, {"rets": [], "stops": 0})
        a["rets"].append(ret)
        if hit:
            a["stops"] += 1
    out = {}
    for sig, a in agg.items():
        r = np.array(a["rets"])
        out[sig] = {"n": len(r), "win_rate": round((r > 0).mean() * 100, 1),
                    "mean": round(r.mean(), 2), "median": round(float(np.median(r)), 2),
                    "stop_rate": round(a["stops"] / len(r) * 100, 1)}
    return out


def backtest_stock_split(code: str, hold: int, test_days: int):
    """返回 (train_trades, test_trades)：近 test_days 根为样本外测试集，其余为训练集。"""
    d = daily_watch._fetch(code, retries=2)
    if d is None or len(d) < 120:
        return [], []
    allt = backtest_stock(code, hold)  # 复用(已含信号+模拟)；按 t 顺序近似切分
    if not allt:
        return [], []
    cut = max(0, len(allt) - test_days)
    return allt[:cut], allt[cut:]


def run_split(hold: int = 5, max_workers: int = 4, test_days: int = 240) -> Dict:
    """防过拟合分段回测：训练集(早期) vs 测试集(近 test_days≈1年样本外)。
    若测试集期望比训练集大幅下滑 → 该信号疑似过拟合/边际衰减。"""
    uni = _universe()
    tr: List[Tuple[str, float, bool]] = []
    te: List[Tuple[str, float, bool]] = []
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        for a, b in ex.map(lambda c: backtest_stock_split(c, hold, test_days), uni):
            tr.extend(a); te.extend(b)
    return {"hold": hold, "test_days": test_days, "train": _agg(tr), "test": _agg(te)}


def run(hold: int = 5, max_workers: int = 8, exit_mode: str = "fixed") -> Dict:
    uni = _universe()
    codes = list(uni.keys())
    all_trades: List[Tuple[str, float, bool]] = []
    fails = 0
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        for res in ex.map(lambda c: backtest_stock(c, hold, exit_mode), codes):
            if res:
                all_trades.extend(res)
            else:
                fails += 1
    # 汇总
    agg: Dict[str, Dict] = {}
    for sig, ret, hit in all_trades:
        a = agg.setdefault(sig, {"rets": [], "stops": 0})
        a["rets"].append(ret)
        if hit:
            a["stops"] += 1
    summary = {}
    for sig, a in agg.items():
        r = np.array(a["rets"])
        wins = r[r > 0]
        losses = r[r <= 0]
        summary[sig] = {
            "n": len(r),
            "win_rate": round((r > 0).mean() * 100, 1),
            "mean": round(r.mean(), 2),
            "median": round(float(np.median(r)), 2),
            "avg_win": round(wins.mean(), 2) if len(wins) else 0.0,
            "avg_loss": round(losses.mean(), 2) if len(losses) else 0.0,
            "stop_rate": round(a["stops"] / len(r) * 100, 1),
        }
    return {"hold": hold, "exit_mode": exit_mode, "stocks": len(codes), "fails": fails,
            "total_trades": len(all_trades), "by_signal": summary}


if __name__ == "__main__":
    import sys
    h = int(sys.argv[1]) if len(sys.argv) > 1 else 5
    mode = sys.argv[2] if len(sys.argv) > 2 else "fixed"
    s = run(hold=h, exit_mode=mode)
    print(f"=== 回测 持有{s['hold']}日 出场{s['exit_mode']} | 池{s['stocks']}只(失败{s['fails']}) | 总样本{s['total_trades']} ===")
    print(f"{'信号':<22}{'样本':>7}{'胜率%':>7}{'平均%':>8}{'中位%':>8}{'均盈%':>7}{'均亏%':>7}{'止损%':>7}")
    order = sorted(s["by_signal"].items(), key=lambda kv: -kv[1]["mean"])
    for sig, v in order:
        print(f"{sig:<22}{v['n']:>7}{v['win_rate']:>7}{v['mean']:>8}{v['median']:>8}{v['avg_win']:>7}{v['avg_loss']:>7}{v['stop_rate']:>7}")
    print("BT_DONE")
