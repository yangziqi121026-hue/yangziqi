"""个股深度分析（自动带隔夜美股 + 美国新闻外围层）。

输入一个 A 股代码 → 输出六模块 Markdown 深度报告：
  〇、外围环境（隔夜美股指数+科技龙头+SOX + 美国/地缘新闻 + risk-on/off 定调）
  一、近 7 日走势
  二、当前技术状态（MA5/10/20/60、RSI、MACD、量比、距52低、近20、K线）
  三、关键价位（阻力/支撑/多空线/入场/止损/目标/RR）
  四、核心结论（外围+技术+基本面+资金 四维定性 → 分类+操作）
  五、风险
  六、个股新闻 + DeepSeek 研判

严格遵守用户交易规则：量比>1.3 才算放量、站/破 MA5、RSI 30/45/70、破 MA5 止损、
剔除 ST/市值<20亿/上市<60天。个股主力/北向资金本环境取不到 → 资金面降权。
不构成投资建议；所有买点配破 MA5 硬止损。
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

import os
_BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_REPORTS = os.path.join(_BASE, "reports")

# 美国/地缘 新闻关键词（与 morning_report 一致口径）
_FOREIGN_KW = ["美国", "美股", "纳指", "道指", "标普", "美联储", "降息", "加息", "CPI",
               "PCE", "非农", "美债", "美元", "鲍威尔", "特朗普", "英伟达", "甲骨文",
               "台积电", "AMD", "博通", "苹果", "微软", "谷歌", "特斯拉", "OpenAI",
               "出口管制", "关税", "欧洲", "欧央行", "日本", "日银", "韩国", "俄", "乌",
               "伊朗", "中东", "OPEC", "原油", "黄金", "地缘", "以色列", "比特币"]


# ---------- 外围：隔夜美股 ----------
def _us_env() -> Dict:
    """拉隔夜美股指数+龙头+SOX，返回结构化数据 + risk 定调。"""
    idx: List[Dict] = []
    leaders: List[Dict] = []
    try:
        import akshare as ak

        for nm, s in [("纳指", ".IXIC"), ("标普", ".INX"), ("道指", ".DJI"),
                      ("费城半导体SOX", ".SOX")]:
            try:
                d = ak.index_us_stock_sina(symbol=s)
                r = d.iloc[-1]; p = d.iloc[-2]
                chg = (float(r["close"]) / float(p["close"]) - 1) * 100
                idx.append({"name": nm, "close": float(r["close"]), "chg": chg,
                            "date": str(r.get("date", ""))[:10]})
            except Exception:  # noqa: BLE001
                idx.append({"name": nm, "close": None, "chg": None, "date": ""})
        for nm, s in [("英伟达", "NVDA"), ("台积电", "TSM"), ("AMD", "AMD"), ("博通", "AVGO")]:
            try:
                d = ak.stock_us_daily(symbol=s)
                r = d.iloc[-1]; p = d.iloc[-2]
                chg = (float(r["close"]) / float(p["close"]) - 1) * 100
                leaders.append({"name": nm, "sym": s, "close": float(r["close"]), "chg": chg})
            except Exception:  # noqa: BLE001
                leaders.append({"name": nm, "sym": s, "close": None, "chg": None})
    except Exception:  # noqa: BLE001
        pass

    # risk 定调：以纳指 + SOX 为准
    def _g(name):
        for x in idx:
            if x["name"].startswith(name) and x["chg"] is not None:
                return x["chg"]
        return None

    nasdaq = _g("纳指"); sox = _g("费城")
    tone, tone_note = "中性", "外围方向不明，按个股自身节奏。"
    vals = [v for v in (nasdaq, sox) if v is not None]
    if vals:
        worst = min(vals)
        best = max(vals)
        if worst <= -1.5:
            tone = "🔴 外围逆风（risk-off）"
            tone_note = "隔夜美股/半导体明显杀跌，科技算力是被砸方向——追高风险大，优先防御、轻仓。"
        elif best >= 1.0 and worst >= -0.3:
            tone = "🟢 外围顺风（risk-on）"
            tone_note = "隔夜美股偏暖，科技算力有外围支撑——可顺势但仍守纪律、破位止损。"
        else:
            tone = "🟡 外围中性偏弱" if worst < -0.5 else "🟡 外围中性"
            tone_note = "外围方向不明朗，别被单日消息脉冲带节奏，跟个股技术走。"
    return {"idx": idx, "leaders": leaders, "tone": tone, "tone_note": tone_note,
            "nasdaq": nasdaq, "sox": sox}


def _foreign_news(limit: int = 6) -> List[str]:
    try:
        import akshare as ak

        df = ak.stock_info_global_em().rename(columns={"标题": "t", "发布时间": "tm"})
        hits = []
        for _, x in df.iterrows():
            if any(k in str(x["t"]) for k in _FOREIGN_KW):
                hits.append(f"- [{str(x['tm'])[:16]}] {str(x['t'])[:60]}")
            if len(hits) >= limit:
                break
        return hits or ["- 暂无命中海外关键词的快讯，需核验"]
    except Exception as exc:  # noqa: BLE001
        return [f"- 海外快讯获取失败：{exc}"]


def _stock_news(code: str, limit: int = 3) -> List[str]:
    try:
        import akshare as ak

        df = ak.stock_news_em(symbol=code)
        cols = {c: c for c in df.columns}
        tcol = "新闻标题" if "新闻标题" in cols else df.columns[1]
        dcol = "发布时间" if "发布时间" in cols else df.columns[-1]
        out = []
        for _, x in df.head(limit).iterrows():
            out.append(f"- {str(x[tcol])[:50]} ｜ {str(x[dcol])[:16]}")
        return out or ["- 暂无个股新闻"]
    except Exception as exc:  # noqa: BLE001
        return [f"- 个股新闻获取失败：{exc}"]


# ---------- 个股 K 线 ----------
def _sina(c: str) -> str:
    return ("sh" if c[0] == "6" else ("sz" if c[0] in "03" else "bj")) + c


def _fetch(code: str, retries: int = 3):
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


def _name(code: str) -> str:
    try:
        import akshare as ak

        info = ak.stock_individual_info_em(symbol=code)
        row = info[info["item"] == "股票简称"]
        if not row.empty:
            return str(row.iloc[0]["value"])
    except Exception:  # noqa: BLE001
        pass
    return code


def _tech(code: str, name: str, d: pd.DataFrame) -> Dict:
    """算全套技术指标 + 信号 + 价位（与 daily_watch 同口径）。"""
    d = indicators.compute_all(d).reset_index(drop=True)
    r = d.iloc[-1]
    close = float(r["close"]); ma5 = float(r.MA5); ma10 = float(r.MA10)
    ma20 = float(r.MA20); ma60 = float(r.MA60); rsi = float(r.RSI14)
    h = d["MACD_Hist"]; h1 = float(h.iloc[-1]); h0 = float(h.iloc[-2]) if len(h) > 1 else h1
    if h1 > 0 and h0 <= 0:
        macd = "翻红(动能转强)"
    elif h1 > 0:
        macd = "红柱" + ("放大" if h1 > h0 else "缩短")
    elif h1 < 0 and h1 > h0:
        macd = "绿柱缩短(跌势趋缓)"
    else:
        macd = "绿柱放大(跌势加重)"
    low5 = float(d["low"].tail(5).min())
    high20 = float(d["high"].tail(20).max())
    low52 = float(d["low"].tail(250).min())
    high52 = float(d["high"].tail(250).max())
    chg20 = (close / float(d["close"].iloc[-21]) - 1) * 100 if len(d) > 21 else 0.0
    dist52 = (close / low52 - 1) * 100 if low52 > 0 else -1
    prev5 = float(d["volume"].iloc[-6:-1].mean()) if len(d) > 6 else float(r["volume"])
    volr = float(r["volume"]) / prev5 if prev5 else 0
    turn = float(r["turnover"]) * 100 if "turnover" in d.columns else None
    cap = float(r["outstanding_share"]) * close / 1e8 if "outstanding_share" in d.columns else None
    cap_ok = cap is not None and 20 <= cap <= 500
    above5 = close >= ma5
    # 近7日
    recent = []
    for _, x in d.tail(7).iterrows():
        o, hh, ll, cc = float(x["open"]), float(x["high"]), float(x["low"]), float(x["close"])
        pc = None
        recent.append({"date": str(x.get("date", ""))[:10], "o": o, "h": hh, "l": ll, "c": cc})
    for i in range(1, len(recent)):
        pc = recent[i - 1]["c"]
        recent[i]["chg"] = (recent[i]["c"] / pc - 1) * 100 if pc else 0.0
    if recent:
        recent[0]["chg"] = 0.0

    # 信号
    if close < ma5 * 0.99:
        signal = "🔴破位预警" + ("(放量)" if volr > 1.3 else "(缩量)")
    elif rsi <= 30:
        signal = "🔵超卖埋伏(禁买)"
    elif above5 and ma5 > ma10 and volr > 1.3 and h1 > 0 and rsi >= 45:
        signal = "✅放量突破/多头"
    elif above5 and abs(close / ma5 - 1) <= 0.025 and volr < 1.0:
        signal = "🟢回踩低吸位(缩量)"
    elif above5:
        signal = "⚪站上MA5·观望"
    else:
        signal = "⚪观望"

    entry = f"{round(min(ma5, low5), 2)}~{round(ma5, 2)}" if above5 else f"回踩{round(ma5, 2)}企稳不破才看"
    stop = round(min(ma5 * 0.99, low5), 2)
    target = round(high20, 2)
    risk = close - stop
    # 仅在「站上MA5、可在现价附近进场」时 RR 才有意义；破位/跌破MA5 时按现价算 RR 是误导
    rr = round((target - close) / risk, 2) if (above5 and risk > 0) else None

    return {
        "code": code, "name": name, "close": round(close, 2), "rsi": round(rsi, 1),
        "macd": macd, "macd_hist": round(h1, 4), "ma5": round(ma5, 2), "ma10": round(ma10, 2),
        "ma20": round(ma20, 2), "ma60": round(ma60, 2), "volr": round(volr, 2),
        "turn": round(turn, 2) if turn is not None else None, "chg20": round(chg20, 2),
        "dist52": round(dist52, 1), "low5": round(low5, 2), "high20": round(high20, 2),
        "low52": round(low52, 2), "high52": round(high52, 2),
        "cap": round(cap) if cap else None, "cap_ok": cap_ok, "above5": above5,
        "signal": signal, "entry": entry, "stop": stop, "target": target, "rr": rr,
        "recent": recent,
    }


def _deepseek(t: Dict, us: Dict, theme: str = "—", fund: str = "—") -> str:
    """调 DeepSeek 研判（把外围 risk 定调塞进大盘环境）。"""
    try:
        from . import deepseek_analyst

        market_env = {
            "trend": us["tone"],
            "volume": f"纳指{_fmt(us['nasdaq'])}、SOX{_fmt(us['sox'])}",
            "sentiment": us["tone_note"],
            "suggested_position": "逆风日≤2成、顺风日≤3成、中性观望",
        }
        cand = {
            "code": t["code"], "name": t["name"], "price": t["close"], "rsi": t["rsi"],
            "macd_state": t["macd"], "ma5": t["ma5"], "ma10": t["ma10"], "ma20": t["ma20"],
            "ma60": t["ma60"], "dist_52w_low_pct": t["dist52"], "chg20": t["chg20"],
            "vol_ratio": t["volr"], "turnover": t["turn"], "float_cap_yi": t["cap"],
            "theme": theme, "fund_status": fund, "entry_low": t["entry"].split("~")[0],
            "entry_high": t["entry"], "stop": t["stop"], "target": t["target"], "rr": t["rr"],
        }
        return deepseek_analyst.analyze_one(cand, market_env)
    except Exception as exc:  # noqa: BLE001
        return f"> ⚠️ DeepSeek 研判失败：{exc}"


def _fmt(v):
    return f"{v:+.2f}%" if v is not None else "—"


def analyze(code: str, name: Optional[str] = None, theme: str = "—",
            fund: str = "—", save: bool = True,
            us: Optional[Dict] = None, fnews: Optional[List[str]] = None,
            include_env: bool = True, heading: str = "#") -> str:
    """生成个股深度报告 Markdown（含隔夜美股+美国新闻外围层）。

    name 可手动传入（本环境东财名称接口取不到时回退为代码）。
    us/fnews 可由外部预取后传入（多只批量时避免重复拉美股/新闻）。
    include_env=False 时不重复渲染外围大段（用于批量报告，外围只在顶部出现一次）。
    heading 控制标题层级（批量嵌入时用 "###"）。
    """
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    if us is None:
        us = _us_env()
    if fnews is None:
        fnews = _foreign_news()
    d = _fetch(code)
    name = name or _name(code)
    title_nm = code if name == code else f"{name} {code}"
    h2 = heading + "#"
    L: List[str] = [f"{heading} {title_nm} 深度分析（含隔夜美股+美国新闻）", f"_{now}_", ""]

    # 〇 外围
    if include_env:
        L.append(f"{h2} 〇、外围环境（隔夜美股 + 美国新闻）")
        L.append(f"**定调：{us['tone']}** — {us['tone_note']}")
        L.append("")
        L.append("**隔夜美股：**")
        for x in us["idx"]:
            L.append(f"- {x['name']}：{x['close'] if x['close'] is not None else '取数失败,需核验'}"
                     + (f"（{_fmt(x['chg'])}）｜{x['date']}" if x["chg"] is not None else ""))
        L.append("")
        L.append("**美股科技龙头（映射A股算力/半导体情绪）：**")
        for x in us["leaders"]:
            L.append(f"- {x['name']} {x['sym']}："
                     + (f"{x['close']:.2f}（{_fmt(x['chg'])}）" if x["close"] is not None else "取数失败,需核验"))
        L.append("")
        L.append("**美国/地缘新闻：**")
        L += fnews
        L.append("")

    if d is None:
        L.append(f"{h2} ⚠️ 个股 K 线获取失败（{code}），无法出技术结论，需核验网络/代码。")
        report = "\n".join(L)
        _save(report, code, name, save)
        return report

    t = _tech(code, name, d)

    # 一 走势
    L.append(f"{h2} 一、近 7 日走势")
    L.append("| 日期 | 收盘 | 涨跌 | 振幅参考(高/低) |")
    L.append("|---|---|---|---|")
    for x in t["recent"]:
        L.append(f"| {x['date']} | {x['c']:.2f} | {x.get('chg', 0):+.2f}% | {x['h']:.2f}/{x['l']:.2f} |")
    L.append("")

    # 二 技术状态
    pos = lambda ma: "站上" if t["close"] >= ma else "跌破"  # noqa: E731
    L.append(f"{h2} 二、当前技术状态")
    L.append(f"- 现价 **{t['close']}**｜{pos(t['ma5'])}MA5 {t['ma5']}、{pos(t['ma10'])}MA10 {t['ma10']}、"
             f"{pos(t['ma20'])}MA20 {t['ma20']}、{pos(t['ma60'])}MA60 {t['ma60']}")
    rsi_tag = "超卖<30" if t["rsi"] < 30 else ("弱势<45" if t["rsi"] < 45 else ("超买>70" if t["rsi"] > 70 else "中性区"))
    L.append(f"- RSI14 **{t['rsi']}**（{rsi_tag}）｜MACD柱 **{t['macd']}**")
    vol_tag = "放量(>1.3)" if t["volr"] > 1.3 else "未放量"
    L.append(f"- 量比 **{t['volr']}**（{vol_tag}）｜换手 {t['turn']}%｜近20日 {t['chg20']}%｜距52周低 {t['dist52']}%")
    L.append(f"- 52周高/低 {t['high52']}/{t['low52']}｜近20高 {t['high20']}｜近5低 {t['low5']}｜"
             f"流通市值 {t['cap']}亿{'⚠超20-500亿区间,降级' if t['cap'] and not t['cap_ok'] else ''}")
    L.append(f"- **信号：{t['signal']}**")
    L.append("")

    # 三 关键价位
    L.append(f"{h2} 三、关键价位")
    L.append(f"- **阻力**：MA5 {t['ma5']} → MA10 {t['ma10']} → MA20 {t['ma20']} → 近20高 {t['high20']}")
    L.append(f"- **现价**：{t['close']}")
    L.append(f"- **支撑**：近5低 {t['low5']} → 52周低 {t['low52']}")
    L.append(f"- **多空线**：MA10 {t['ma10']}（站上偏强/跌破偏弱）")
    rr_txt = f"RR **{t['rr']}**" if t["rr"] is not None else "RR **不适用（已破MA5，须等回踩站回再评估）**"
    L.append(f"- 引擎价位：入场 **{t['entry']}**｜止损 **{t['stop']}**（破MA5）｜目标 **{t['target']}**｜{rr_txt}")
    L.append("")

    # 四 核心结论（四维）
    L.append(f"{h2} 四、核心结论（外围+技术+基本面+资金 四维）")
    env_bad = (us["nasdaq"] is not None and us["nasdaq"] <= -1.0) or (us["sox"] is not None and us["sox"] <= -1.5)
    tech_bad = (not t["above5"]) or "破位" in t["signal"]
    L.append(f"| 维度 | 状态 |")
    L.append(f"|---|---|")
    L.append(f"| 外围 | {us['tone']}（纳指{_fmt(us['nasdaq'])}/SOX{_fmt(us['sox'])}）{'❌逆风' if env_bad else '—'} |")
    L.append(f"| 技术 | {t['signal']}、{'空头/跌破均线' if tech_bad else '站均线'}、量比{t['volr']} |")
    L.append(f"| 基本面 | {fund} |")
    L.append(f"| 资金 | 量比{t['volr']}{'(无承接)' if t['volr'] < 1.0 else ''}（主力/北向取不到,降权） |")
    L.append("")
    # 操作建议
    if t["rsi"] <= 30:
        op = ("🔵 **超卖埋伏但禁买**：现价禁追，等放量反包+站回MA5再看；"
              f"破 {t['low5']} 继续看低。")
    elif "破位" in t["signal"]:
        op = (f"🔴 **破位/下跌中继，不碰**：持有者反抽 MA10 {t['ma10']} 不站上就走、跌破 {t['stop']} 止损；"
              "空仓别抄，等企稳信号。"
              + ("外围逆风更要回避。" if env_bad else ""))
    elif t["signal"] == "✅放量突破/多头" and (t["rr"] or 0) >= 1.5 and not env_bad and t["cap_ok"]:
        op = (f"✅ **可关注（四重共振待确认）**：站上MA5+放量+RR{t['rr']}；"
              f"入场 {t['entry']}、破 {t['stop']} 止损、目标 {t['target']}；首仓1成、总仓≤3成。"
              + ("⚠外围非顺风，仓位再降一档。" if us["nasdaq"] is not None and us["nasdaq"] < 0 else ""))
    elif t["above5"]:
        rr_lo = "（RR偏低）" if (t["rr"] is not None and t["rr"] < 1.5) else ""
        op = (f"⚪ **站上MA5但未共振，观望/极小仓**：回踩 {t['entry']} 不破再看，破 {t['stop']} 走{rr_lo}。"
              + ("外围逆风优先等。" if env_bad else ""))
    else:
        op = f"⚪ **跌破MA5、观望**：等回踩 MA5 {t['ma5']} 企稳站回再看，破 {t['stop']} 不看。"
    L.append(f"**操作：** {op}")
    L.append("")

    # 五 风险
    L.append(f"{h2} 五、风险")
    risks = []
    if env_bad:
        risks.append("外围逆风未解（隔夜美股/半导体杀跌），题材短期无风口")
    if "破位" in t["signal"]:
        risks.append(f"已破MA5/下跌中继，破 {t['stop']} 加速下行")
    if t["volr"] < 1.0:
        risks.append("缩量无承接，反抽乏力")
    if t["cap"] and not t["cap_ok"]:
        risks.append(f"流通市值 {t['cap']}亿 超出20-500亿区间")
    if t["rsi"] > 70:
        risks.append("RSI超买，短期回调压力")
    risks.append("个股主力/北向资金本环境取不到，资金面为降权估计")
    for rk in risks:
        L.append(f"- {rk}")
    L.append("")

    # 六 新闻 + DeepSeek
    L.append(f"{h2} 六、个股新闻 + DeepSeek 研判")
    L.append("**个股新闻：**")
    L += _stock_news(code)
    L.append("")
    L.append("**DeepSeek（外围已注入大盘环境）：**")
    L.append(_deepseek(t, us, theme, fund))
    L.append("")

    L.append("> 规则：量比>1.3才算放量、站/破MA5、RSI 30/45/70、破MA5硬止损、市值20-500亿(超出降级)。")
    L.append("> 资金面(主力/北向)未取到、降权；标「需核验」处以实盘为准。本报告仅供研究，不构成投资建议。")

    report = "\n".join(L)
    _save(report, code, name, save)
    return report


def _save(report: str, code: str, name: str, save: bool):
    if not save:
        return
    os.makedirs(_REPORTS, exist_ok=True)
    tag = code if name == code else f"{code}{name}"
    path = os.path.join(_REPORTS, f"深度_{tag}_{datetime.now().strftime('%Y%m%d')}.md")
    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write(report)
        print(f"[stock_deepdive] 已保存：{path}")
    except Exception as exc:  # noqa: BLE001
        print(f"[stock_deepdive] 保存失败：{exc}")


if __name__ == "__main__":
    import sys

    _code = sys.argv[1] if len(sys.argv) > 1 else "603516"
    _name = sys.argv[2] if len(sys.argv) > 2 else None
    _theme = sys.argv[3] if len(sys.argv) > 3 else "—"
    _fund = sys.argv[4] if len(sys.argv) > 4 else "—"
    print(analyze(_code, name=_name, theme=_theme, fund=_fund))
