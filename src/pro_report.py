"""⑩ 个股分析页·专业版收口（P6）。

把已就绪模块汇成用户要求的固定 10 行表：
  题材 / 技术 / 财报 / 估值 / 同行 / 股东 / 产业价格 / 事件 / 风险 / 操作

并守住既有 9 条铁律：顶部带隔夜美股外围 + 第一止盈 + 数据时效戳 +（可选）DeepSeek。
未就绪模块（⑤产业价格 / ②⑥订单产能）显示"待接入"，做完直接替换该行。

用法：
    print(pro_card("002929", "润建股份"))            # 纯专业版10行表
    print(pro_card("002929", ds=True))               # 额外调 DeepSeek 置信度门控
"""
from __future__ import annotations

from typing import Dict, Optional

import pandas as pd

try:
    pd.set_option("future.infer_string", False)
except Exception:  # noqa: BLE001
    pass

from . import stock_deepdive as sd
from .fundamentals import financial_quarter_tracker as fqt
from .fundamentals import fundamental_score as fs
from .fundamentals import holder_change_tracker as hct
from .fundamentals import peer_compare as pc
from .fundamentals import event_calendar as ec
from .fundamentals import annual_report_parser as arp


def _decision(tech: Dict, fund_tier: Optional[str], ds_conf: Optional[str]) -> str:
    """技术信号 + 基本面档 + DeepSeek → 最终入池结论。技术为硬门槛。"""
    sig = tech.get("signal", "")
    # 技术硬门槛
    if "破位" in sig:
        return "🔴 不碰（技术破位，等放量站回MA5企稳）"
    if "超卖" in sig and "禁买" in sig:
        return "🔵 禁买（超卖埋伏，等放量反包站回MA5）"
    confirmed = tech.get("confirmed")  # 站MA5+放量
    if confirmed:
        if ds_conf == "低":
            return "⚠️ 谨慎（技术达标但DeepSeek置信低，仅轻仓回踩进、硬止损）"
        if fund_tier in ("强基本面", "改善中"):
            return "🟢 入池（技术达标 + 基本面共振，首仓1成，回踩低吸更佳）"
        if fund_tier and "题材" in fund_tier:
            return "🟡 入池-仅题材博弈（基本面平庸，轻仓+破MA5硬止损，不可重仓）"
        if fund_tier == "风险较大":
            return "⚠️ 极谨慎（技术可博弈但基本面差，极轻仓试错或放弃）"
        return "🟢 入池（技术达标，回踩低吸，破MA5止损）"
    # 站MA5未放量 / 回踩
    return "⏳ 观察（站MA5未放量/未共振，等量比>1.3放量站MA10再进）"


def _risk_flags(tech, fin, val, holder, events) -> str:
    flags = []
    sig = tech.get("signal", "")
    if "破位" in sig:
        flags.append("技术破位")
    if val and val.get("PE_TTM") is not None and val["PE_TTM"] < 0:
        flags.append("无盈利(PE为负)")
    elif val and val.get("PE_TTM") and val["PE_TTM"] > 80:
        flags.append(f"高估(PE{val['PE_TTM']:.0f})")
    if fin and fin.get("score") is not None and fin["score"] < 40:
        flags.append(f"财报弱({fin['score']}分)")
    cf = None
    if fin and fin.get("breakdown", {}).get("现金流改善"):
        cf = fin["breakdown"]["现金流改善"][1]
        if "经营现金流-" in cf:
            flags.append("经营现金流为负")
    if holder and holder.get("tier") == "筹码恶化":
        flags.append("筹码恶化")
    nh = holder.get("户数", {}) if holder else {}
    if nh.get("户数环比%") and nh["户数环比%"] > 8:
        flags.append(f"户数+{nh['户数环比%']:.0f}%分散")
    # 解禁/业绩预告
    nxt = events.get("近端解禁") if events else None
    if nxt:
        flags.append(f"解禁{nxt[0]['日期']}({nxt[0]['解禁市值(亿)']}亿)")
    fc = events.get("业绩预告") if events else None
    if fc and fc.get("净利变动", "").startswith("-"):
        flags.append(f"业绩预告负({fc['净利变动']})")
    return "；".join(flags) if flags else "无重大硬伤（仍守破MA5止损）"


def pro_card(code: str, name: str = "", ds: bool = False, top: int = 5,
             theme: Optional[str] = None) -> str:
    """生成专业版固定 10 行表（含外围/第一止盈/数据时效）。

    theme: 若给定题材（如"算力"/"HBM"），题材行与订单产能维度按业务验证(②⑥)落地判断。
    """
    # 技术 + K线
    d = sd._fetch(code)
    if d is None:
        return f"## {name} {code} 专业版分析\n> 取数失败（东财限流/代码异常）"
    tech = sd._tech(code, name or code, d)
    # 放量站MA10确认（与选股门槛同口径）
    tech["confirmed"] = (tech.get("close") is not None and tech.get("ma10") is not None
                         and tech["close"] >= tech["ma10"] and (tech.get("volr") or 0) > 1.3)
    if not name:
        name = tech.get("name") or code
    # 外围
    env = sd._us_env()
    # 基本面各维
    fin_df = fqt.fetch_quarters(code, 8)
    fin = fqt.score(fin_df) if not fin_df.empty else {}
    val = pc.valuation(code)
    comp = pc.compare(code, top=top, with_kline=False)
    rank = pc.rank_value(comp) if not comp.empty else comp
    holder = hct.summarize(code, name)
    events = ec.upcoming(code, name, days=7)
    fund = fs.total_score(code, name, theme=theme)
    # DeepSeek 置信（可选）
    ds_conf = None
    if ds:
        try:
            from . import deepseek_analyst
            ds_conf = deepseek_analyst.assess_confidence(
                {"code": code, "name": name, "signal": tech.get("signal"),
                 "rsi": tech.get("rsi"), "volr": tech.get("volr")},
                {"trend": env["tone"]})
        except Exception:  # noqa: BLE001
            ds_conf = None

    # —— 各行结论 ——
    # 题材（给定theme则做业务验证，否则显示行业）
    if theme:
        tb = arp.verify_theme_benefit(code, theme)
        theme_row = (f"「{theme}」{tb['benefit']}(置信{tb['confidence']})——{tb['note']}"
                     f"｜行业{val.get('行业','—')}｜外围{env['tone']}")
    else:
        theme_row = f"{val.get('行业','—')}（未指定题材；体系/强度待接题材雷达；外围{env['tone']}）"
    # 技术
    tech_row = (f"{tech['signal']}｜现价{tech['close']} MA5={tech['ma5']}/MA10={tech['ma10']} "
                f"量比{tech['volr']} RSI{tech['rsi']}")
    # 财报
    if fin:
        ac = fin.get("accel", {})
        fin_row = f"{fin['score']}/100（{fin['period']}；营收加速{ac.get('营收加速')}/净利加速{ac.get('净利加速')}）"
    else:
        fin_row = "无财务数据"
    # 估值
    if val and val.get("PE_TTM") is not None:
        val_row = (f"PE_TTM{val['PE_TTM']:.0f}/PE静{val.get('PE静') and round(val['PE静'])}"
                   f"/PB{val.get('PB') and round(val['PB'],2)}/PEG{val.get('PEG') and round(val['PEG'],1)}"
                   f"｜总市值{val.get('总市值(亿)')}亿")
    else:
        val_row = "无估值数据"
    # 同行
    if not rank.empty:
        tr = rank.index[rank["代码"] == code].tolist()
        rk = (tr[0] + 1) if tr else "—"
        peer_row = f"{val.get('行业')} 性价比 第{rk}/{len(rank)}（性价比分{rank.loc[rank['代码']==code,'性价比分'].iloc[0] if tr else '—'}）"
    else:
        peer_row = "无同行数据"
    # 股东
    holder_row = f"{holder['score']}/100 {holder['tier']}（{'；'.join(holder['notes']) or '无异动'}）" if holder else "无数据"
    # 产业价格（P5）
    price_row = "待P5接入（DRAM/铜/稀土/制冷剂等行业价格周期）"
    # 事件
    ev = events.get("未来事件", [])
    ev_row = ("；".join(f"{e['日期']}{e['类别']}" for e in ev) if ev else "未来7天无个股重大事件")
    if events.get("下次财报"):
        ev_row += f"；下次财报{events['下次财报']['日期']}"
    # 风险
    risk_row = _risk_flags(tech, fin, val, holder, events)
    # 操作（含第一止盈）
    decision = _decision(tech, fund.get("tier"), ds_conf)
    tp1 = tech.get("ma20") or tech.get("high20")
    op_row = (f"{decision}｜入场{tech.get('entry')} 止损{tech.get('stop')} "
              f"第一止盈{tp1}(减半) 目标{tech.get('target')} RR{tech.get('rr')}")
    if ds_conf:
        op_row += f"｜DeepSeek={ds_conf}"

    # —— 组装 ——
    stale = sd._stale_note(tech.get("data_date", "")) if hasattr(sd, "_stale_note") else ""
    综合 = f"{fund['score']}/100 → {fund['tier']}" if fund.get("score") is not None else "数据不足"
    lines = [
        f"## 📋 {name} {code} 专业版分析（综合基本面 {综合}）",
        f"> 🕒 {stale}　|　外围：{env['tone']}（纳指{sd._fmt(env['nasdaq'])}/SOX{sd._fmt(env['sox'])}）",
        "",
        "| 模块 | 结论 |",
        "|---|---|",
        f"| 题材 | {theme_row} |",
        f"| 技术 | {tech_row} |",
        f"| 财报 | {fin_row} |",
        f"| 估值 | {val_row} |",
        f"| 同行 | {peer_row} |",
        f"| 股东 | {holder_row} |",
        f"| 产业价格 | {price_row} |",
        f"| 事件 | {ev_row} |",
        f"| 风险 | {risk_row} |",
        f"| 操作 | {op_row} |",
        "",
        "> 专业版收口：技术为硬门槛，基本面定仓位与持有信心；破MA5一律硬止损。仅研究，不构成投资建议。",
    ]
    return "\n".join(lines)
