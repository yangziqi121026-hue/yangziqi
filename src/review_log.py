"""复盘日志：把每次"明日候选"推荐落库，次日自动比对真实走势，算胜率/止损率。

目的：用数据约束分析者（而非靠自觉）。每条推荐记录 rec_close/入场/止损/目标，
次个交易日用真实日线比对：方向对错、是否触及止损、是否达第一止盈，
汇总出 总胜率 / 平均次日涨跌 / 止损触发率 / 分奖牌胜率。

口径说明（透明）：outcome 以"推荐日收盘价 → 下一交易日收盘价"的方向衡量
（相当于"在推荐价附近参与，次日方向对错"的代理指标），并单独标注是否破止损。
对"等回踩/等放量"类未必当日成交的推荐，这是偏保守的近似，但足以暴露我的系统性偏差。

数据：新浪日线（前复权）。不构成投资建议。
"""

import json
import os
from datetime import datetime
from typing import Dict, List, Optional

_BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_LOG = os.path.join(_BASE, "reports", "复盘日志.jsonl")


def _read() -> List[Dict]:
    if not os.path.exists(_LOG):
        return []
    out = []
    with open(_LOG, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    out.append(json.loads(line))
                except Exception:  # noqa: BLE001
                    pass
    return out


def _write_all(recs: List[Dict]) -> None:
    os.makedirs(os.path.dirname(_LOG), exist_ok=True)
    with open(_LOG, "w", encoding="utf-8") as f:
        for r in recs:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def log_picks(picks: List[Dict], rec_date: Optional[str] = None,
              tone: Optional[str] = None) -> int:
    """把当日候选写入日志（同一 rec_date+code 不重复）。返回新增条数。"""
    rec_date = rec_date or datetime.now().strftime("%Y-%m-%d")
    recs = _read()
    existing = {(r["rec_date"], r["code"]) for r in recs}
    added = 0
    for p in picks:
        key = (rec_date, p.get("code"))
        if key in existing:
            continue
        recs.append({
            "rec_date": rec_date, "code": p.get("code"), "name": p.get("name"),
            "medal": p.get("medal", "-"), "signal": p.get("signal"),
            "rec_close": p.get("close"), "entry": p.get("entry"),
            "stop": p.get("stop"), "target": p.get("target"), "rr": p.get("rr"),
            "tone": tone,
            # 供亏损单5类错误归类的字段
            "ds_conf": p.get("ds_conf"), "is_stale": bool(p.get("is_stale")),
            "tier": p.get("tier"), "turn": p.get("turn"), "rsi": p.get("rsi"),
            "evaluated": False, "eval_date": None, "eval_close": None,
            "chg_pct": None, "hit_stop": None, "hit_tp1": None, "outcome": None,
            "error_type": None,
        })
        added += 1
    _write_all(recs)
    return added


def _default_fetch(code: str):
    from . import stock_deepdive
    return stock_deepdive._fetch(code)


def evaluate(fetch=None) -> int:
    """对所有未评估、且已有更晚交易日数据的记录做比对。返回评估条数。"""
    recs = _read()
    fetch = fetch or _default_fetch
    cache: Dict[str, object] = {}
    changed = 0
    for r in recs:
        if r.get("evaluated"):
            continue
        code = r["code"]
        if code not in cache:
            cache[code] = fetch(code)
        d = cache[code]
        if d is None or len(d) == 0:
            continue
        last = d.iloc[-1]
        ld = str(last.get("date", ""))[:10]
        if not ld or ld <= r["rec_date"]:
            continue  # 数据还没推进到推荐日之后
        close = float(last["close"]); high = float(last["high"]); low = float(last["low"])
        rc = r.get("rec_close") or close
        r["eval_date"] = ld
        r["eval_close"] = round(close, 2)
        r["chg_pct"] = round((close / rc - 1) * 100, 2) if rc else None
        r["hit_stop"] = (r.get("stop") is not None) and (low <= float(r["stop"]))
        r["hit_tp1"] = (r.get("target") is not None) and (high >= float(r["target"]))
        if r["hit_stop"]:
            r["outcome"] = "止损"
        elif r["chg_pct"] is not None and r["chg_pct"] > 0:
            r["outcome"] = "对(涨)"
        else:
            r["outcome"] = "错(跌)"
        # 亏损单(含止损)归到5类错误(启发式)
        if not (r["outcome"] or "").startswith("对"):
            r["error_type"] = _classify_error(r)
        r["evaluated"] = True
        changed += 1
    if changed:
        _write_all(recs)
    return changed


def _classify_error(r: Dict) -> str:
    """把亏损单归到5类错误(启发式，基于已存字段)：
    ①数据错误 ②规则混用 ③风控漏判 ④题材误判 ⑤流动性踩坑。"""
    if r.get("is_stale"):
        return "①数据错误(用了滞后数据)"
    if r.get("rr") is not None and r["rr"] < 1.5:
        return "③风控漏判(RR<1.5仍推)"
    if r.get("rsi") is not None and r["rsi"] >= 70:
        return "③风控漏判(超买仍推)"
    sig = r.get("signal") or ""
    if "破位" in sig or "超卖" in sig:
        return "③风控漏判(破位/超卖禁买区)"
    tier = r.get("tier") or ""
    if "超跌" in tier or "题材" in tier:
        return "④题材误判(题材未兑现/退潮)"
    return "④题材/择时误判(逻辑未兑现)"  # 兜底；⑤流动性需成交额数据，暂未采集


def errors_md() -> str:
    recs = [r for r in _read() if r.get("evaluated") and r.get("error_type")]
    if not recs:
        return "（暂无已归类的亏损单。）"
    from collections import Counter
    c = Counter(r["error_type"] for r in recs)
    lines = [f"**亏损单错误归类（共{len(recs)}笔）：**"]
    for et, n in c.most_common():
        lines.append(f"- {et}：{n}笔")
    return "\n".join(lines)


def scorecard() -> Dict:
    """汇总已评估记录。"""
    recs = [r for r in _read() if r.get("evaluated")]
    total = len(recs)
    if not total:
        return {"total": 0}
    wins = sum(1 for r in recs if (r.get("outcome") or "").startswith("对"))
    stops = sum(1 for r in recs if r.get("hit_stop"))
    chg_vals = [r["chg_pct"] for r in recs if r.get("chg_pct") is not None]
    avg = round(sum(chg_vals) / len(chg_vals), 2) if chg_vals else None
    # 分奖牌
    by_medal: Dict[str, Dict] = {}
    for r in recs:
        m = r.get("medal", "-")
        b = by_medal.setdefault(m, {"n": 0, "win": 0, "sum": 0.0})
        b["n"] += 1
        if (r.get("outcome") or "").startswith("对"):
            b["win"] += 1
        if r.get("chg_pct") is not None:
            b["sum"] += r["chg_pct"]
    return {
        "total": total, "wins": wins, "win_rate": round(wins / total * 100, 1),
        "stops": stops, "stop_rate": round(stops / total * 100, 1), "avg_chg": avg,
        "by_medal": by_medal,
    }


def scorecard_md() -> str:
    s = scorecard()
    if s.get("total", 0) == 0:
        return "（复盘日志暂无已评估记录——从下一个交易日起开始累计。）"
    lines = [
        f"**累计推荐 {s['total']} 次** ｜ 方向胜率 **{s['win_rate']}%**（{s['wins']}/{s['total']}）"
        f" ｜ 平均次日涨跌 **{s['avg_chg']:+}%** ｜ 触发止损率 **{s['stop_rate']}%**",
    ]
    if s.get("by_medal"):
        lines.append("分奖牌：" + " ｜ ".join(
            f"{m} {b['win']}/{b['n']}（均{round(b['sum']/b['n'],2):+}%）"
            for m, b in sorted(s["by_medal"].items())))
    return "\n".join(lines)


if __name__ == "__main__":
    n = evaluate()
    print(f"评估 {n} 条")
    print(scorecard_md())
