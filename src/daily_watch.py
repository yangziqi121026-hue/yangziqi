"""每日盯盘系统：分层股票池 → 规则化分类 + 信号检测 + 当日分层报告。

严格遵守用户交易规则：量比>1.3 才算放量、站 MA5/MA10、RSI 分界、破 MA5 止损、
流通市值 20–500 亿（超出降级）。

分类：主推 / 二线备选 / 超跌埋伏 / 防御 / 剔除。
信号：放量突破 / 回踩低吸位 / 超卖埋伏 / 破位预警 / 横盘观望。

数据：新浪日线（含换手/流通股本，可算量比/换手/市值），带重试。
个股主力/北向资金本环境取不到 → 资金面降权（用量比/换手/板块新闻代理）。
不构成投资建议；所有买点均配破 MA5 硬止损。
"""

import time
from datetime import datetime
from typing import Dict, List, Optional

import pandas as pd

from . import indicators

try:
    pd.set_option("future.infer_string", False)
except Exception:  # noqa: BLE001
    pass

# 分层观察池（code -> name）。可自由增删。
WATCHLIST: Dict[str, Dict[str, str]] = {
    "主线·机器人": {
        "003021": "兆威机电", "002472": "双环传动", "603728": "鸣志电器",
        "300124": "汇川技术",
    },
    "主线·AI算力": {
        "301236": "软通动力", "000977": "浪潮信息",
    },
    "算力二线·温控电源": {
        "002837": "英维克", "301018": "申菱环境", "300870": "欧陆通",
    },
    "算力二线·超跌": {
        "002261": "拓维信息", "000034": "神州数码", "300442": "润泽科技",
    },
    "防御·电力高股息": {
        "600900": "长江电力", "601985": "中国核电", "600674": "川投能源",
        "600905": "三峡能源",
    },
    "半导体": {
        "002156": "通富微电", "603501": "韦尔股份",
    },
}


def _sina(c: str) -> str:
    return ("sh" if c[0] == "6" else ("sz" if c[0] in "03" else "bj")) + c


def _fetch(code: str, retries: int = 2):
    # 优先直连东财（当日最新）；限流/失败回退新浪。
    try:
        from . import em_fetch

        d = em_fetch.daily(code)
        if d is not None and len(d) >= 60:
            return d
    except Exception:  # noqa: BLE001
        pass
    for _ in range(retries):
        try:
            import akshare as ak

            d = ak.stock_zh_a_daily(symbol=_sina(code), adjust="qfq")
            if d is not None and len(d) >= 60:
                return d
        except Exception:  # noqa: BLE001
            pass
        time.sleep(1.0)
    return None


def _classify(code: str, name: str, tier: str, d: pd.DataFrame) -> dict:
    """对单只票算指标 + 按规则分类 + 给信号/价位。"""
    d = indicators.compute_all(d).reset_index(drop=True)
    r = d.iloc[-1]
    close = float(r["close"]); ma5 = float(r.MA5); ma10 = float(r.MA10); ma20 = float(r.MA20); ma60 = float(r.MA60)
    rsi = float(r.RSI14)
    h = d["MACD_Hist"]
    h1 = float(h.iloc[-1]); h0 = float(h.iloc[-2]) if len(h) > 1 else h1
    just_red = h1 > 0 and h0 <= 0
    red = h1 > 0
    shrink = h1 < 0 and h1 > h0
    macd = "翻红" if just_red else ("红柱" if red else ("绿柱缩短" if shrink else "绿柱放大"))
    low5 = float(d["low"].tail(5).min())
    high20 = float(d["high"].tail(20).max())
    low52 = float(d["low"].tail(250).min())
    chg20 = (close / float(d["close"].iloc[-21]) - 1) * 100 if len(d) > 21 else 0.0
    dist52 = (close / low52 - 1) * 100 if low52 > 0 else -1
    prev5 = float(d["volume"].iloc[-6:-1].mean()) if len(d) > 6 else float(r["volume"])
    volr = float(r["volume"]) / prev5 if prev5 else 0
    turn = float(r["turnover"]) * 100 if "turnover" in d.columns else None
    cap = float(r["outstanding_share"]) * close / 1e8 if "outstanding_share" in d.columns else None
    cap_ok = cap is not None and 20 <= cap <= 500
    above5 = close >= ma5
    multihead = ma5 > ma10
    near_ma5 = abs(close / ma5 - 1) <= 0.025 if ma5 else False

    # —— 信号检测 ——
    if close < ma5 * 0.99:
        signal = "🔴破位预警" + ("(放量)" if volr > 1.3 else "(缩量)")
    elif rsi <= 30:
        signal = "🔵超卖埋伏"
    elif above5 and multihead and volr > 1.3 and red and rsi >= 45:
        signal = "✅放量突破/多头"
    elif above5 and near_ma5 and volr < 1.0:
        signal = "🟢回踩低吸位(缩量)"
    elif above5:
        signal = "⚪站上MA5·观望"
    else:
        signal = "⚪观望"

    # —— 分类 ——
    防御 = tier.startswith("防御")
    if 防御:
        category = "防御打底" if above5 or near_ma5 else "防御观察"
    elif "破位" in signal:
        category = "剔除/破位"
    elif signal == "🔵超卖埋伏":
        category = "超跌埋伏(禁买)"
    elif signal == "✅放量突破/多头":
        category = "主推" if cap_ok else "二线备选(超市值)"
    elif signal in ("🟢回踩低吸位(缩量)", "⚪站上MA5·观望"):
        category = "二线备选" if cap_ok else "二线备选(超市值)"
    else:
        category = "观望"

    # —— 价位 ——
    entry = f"{round(min(ma5, low5), 2)}~{round(ma5, 2)}" if above5 else f"回踩{round(ma5, 2)}企稳"
    stop = round(min(ma5 * 0.99, low5), 2)
    target = round(high20, 2)
    risk = close - stop
    rr = round((target - close) / risk, 2) if risk > 0 else 0

    return {
        "code": code, "name": name, "tier": tier, "close": round(close, 2),
        "rsi": round(rsi, 1), "macd": macd, "ma5": round(ma5, 2), "ma10": round(ma10, 2),
        "ma20": round(ma20, 2), "ma60": round(ma60, 2), "volr": round(volr, 2),
        "turn": round(turn, 2) if turn is not None else None, "chg20": round(chg20, 2),
        "dist52": round(dist52, 1), "cap": round(cap) if cap else None, "cap_ok": cap_ok,
        "signal": signal, "category": category,
        "entry": entry, "stop": stop, "target": target, "rr": rr,
        "data_date": str(r.get("date", ""))[:10],
    }


# 分类展示顺序
CATEGORY_ORDER = ["主推", "二线备选", "二线备选(超市值)", "防御打底", "防御观察",
                  "超跌埋伏(禁买)", "观望", "剔除/破位"]


def scan_watchlist(progress_callback=None) -> Dict:
    """扫描分层观察池，返回 {rows, by_category, alerts, meta}。"""
    rows: List[dict] = []
    fails: List[str] = []
    all_items = [(tier, c, n) for tier, d in WATCHLIST.items() for c, n in d.items()]
    total = len(all_items)
    for i, (tier, code, name) in enumerate(all_items):
        if progress_callback:
            progress_callback(f"{i+1}/{total} {name}", (i + 1) / total)
        d = _fetch(code)
        if d is None:
            fails.append(f"{code}{name}")
            continue
        try:
            rows.append(_classify(code, name, tier, d))
        except Exception as exc:  # noqa: BLE001
            fails.append(f"{code}{name}(算错:{exc})")

    by_cat: Dict[str, List[dict]] = {}
    for r in rows:
        by_cat.setdefault(r["category"], []).append(r)
    for k in by_cat:
        by_cat[k].sort(key=lambda x: -x["rr"])

    # 当日提醒：放量突破 / 破位 / 回踩到位 / 超卖
    alerts = [r for r in rows if r["signal"] in ("✅放量突破/多头", "🟢回踩低吸位(缩量)")
              or "破位" in r["signal"]]
    return {
        "rows": rows, "by_category": by_cat, "alerts": alerts,
        "meta": {"time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                 "scanned": len(rows), "fails": fails, "total": total},
    }


def build_report_md(result: Dict) -> str:
    """生成当日分层 Markdown 报告。"""
    m = result["meta"]
    lines = [f"# 每日盯盘报告 {m['time']}",
             f"扫描 {m['scanned']}/{m['total']}（失败 {len(m['fails'])}）｜资金面降权｜不构成投资建议\n"]
    # 提醒
    if result["alerts"]:
        lines.append("## 🚨 今日信号提醒")
        for r in result["alerts"]:
            lines.append(f"- **{r['signal']}** {r['code']} {r['name']}（{r['tier']}）"
                         f"现价{r['close']} 量比{r['volr']} RSI{r['rsi']} → 入场{r['entry']} 止损{r['stop']} 目标{r['target']} RR{r['rr']}")
        lines.append("")
    # 分类
    for cat in CATEGORY_ORDER:
        items = result["by_category"].get(cat, [])
        if not items:
            continue
        lines.append(f"## {cat}（{len(items)}）")
        for r in items:
            cap = f"{r['cap']}亿" + ("⚠超规" if not r["cap_ok"] else "") if r["cap"] else "—"
            lines.append(f"- {r['code']} {r['name']}｜收{r['close']}｜RSI{r['rsi']}｜{r['macd']}｜"
                         f"MA5 {r['ma5']}/MA10 {r['ma10']}｜量比{r['volr']}｜换手{r['turn']}%｜近20 {r['chg20']}%｜"
                         f"距52低{r['dist52']}%｜市值{cap}｜{r['signal']}｜入场{r['entry']} 止损{r['stop']} 目标{r['target']} RR{r['rr']}")
        lines.append("")
    lines.append("> 规则：量比>1.3才算放量、站MA5/MA10、破MA5止损、市值20-500亿（超出降级）。"
                 "资金面(主力/北向)未取到、降权。不构成投资建议。")
    return "\n".join(lines)
