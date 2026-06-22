"""持仓每日跟踪 + 风险自检（自我迭代框架·规则2）。

输入持仓 [{code, name?, cost, shares?}]，逐只：
拉最新行情(标数据日期) → 算浮盈 → 校验止损/止盈/逻辑破位 →
给"持有/减半/清仓"结论 + 动态止损(浮盈达标上移到MA5) + 风险点。

数据：新浪日线(stock_deepdive)。个股主力/北向取不到、降权。不构成投资建议，破MA5严格止损。
"""

from typing import Dict, List, Optional

import pandas as pd

from . import stock_deepdive

try:
    pd.set_option("future.infer_string", False)
except Exception:  # noqa: BLE001
    pass


def _decide(t: Dict, cost: Optional[float]) -> str:
    close, ma5, ma10 = t["close"], t["ma5"], t["ma10"]
    pl = (close / cost - 1) * 100 if cost else None
    if "破位" in t["signal"] or close < ma5 * 0.99:
        return f"🔴 **跌破MA5/破位→减仓或清仓离场**（逻辑已破，破{round(ma5*0.99,2)}无条件走）"
    if close >= t["target"]:
        return f"🟢 **达第一止盈{t['target']}→减半落袋**，剩余移动止损(跌破MA5 {ma5}清)让赢家跑"
    if pl is not None and pl > 0 and close >= ma5:
        return f"🟡 **持有·浮盈{pl:+.1f}%**：动态止损上移到 **MA5 {ma5}**（跌破即清，锁利润）"
    if close >= ma5:
        return f"⚪ **持有观察**：站MA5上方，破 {round(ma5*0.99,2)} 止损"
    return f"🔴 **已在MA5下方→离场**，破 {round(ma5*0.99,2)} 不留"


def track(positions: List[Dict]) -> str:
    L: List[str] = ["# 📋 持仓动态风险自检", ""]
    dates = []
    for p in positions:
        code = str(p["code"]); cost = p.get("cost")
        d = stock_deepdive._fetch(code)
        if d is None:
            L.append(f"## {code} 取数失败，需核验")
            continue
        t = stock_deepdive._tech(code, p.get("name", code), d)
        dates.append(t["data_date"])
        pl = (t["close"] / cost - 1) * 100 if cost else None
        L.append(f"## {p.get('name', code)} {code}　🕒{t['data_date']}")
        L.append(f"- 现价 **{t['close']}**" + (f"｜成本 {cost}｜**浮盈 {pl:+.1f}%**" if cost else "")
                 + f"｜MA5 {t['ma5']}/MA10 {t['ma10']}｜RSI {t['rsi']}｜量比 {t['volr']}｜{t['signal']}")
        L.append(f"- 决策：{_decide(t, cost)}")
        L.append(f"- 关键位：止损(破MA5) {round(t['ma5']*0.99,2)}｜第一止盈 {t['target']}｜近5低 {t['low5']}")
        L.append("")
    if dates:
        latest = max(dates)
        stale = [d for d in dates if d < latest]
        L.insert(1, f"> 🕒 数据日：最新 {latest}"
                 + (f"；⚠️ {len(stale)}只滞后未更新到该日，决策打折" if stale else "（全部当日）") + "\n")
    L.append("> 纪律：破MA5无条件止损；达第一止盈减半、剩余移动止损让赢家跑；单只≤总资金10%、单笔亏损≤2%。不构成投资建议。")
    return "\n".join(L)


if __name__ == "__main__":
    # 示例（替换成你的真实持仓）
    demo = [{"code": "300161", "name": "华中数控", "cost": 31.0},
            {"code": "603516", "name": "淳中科技", "cost": 130.0}]
    print(track(demo))
