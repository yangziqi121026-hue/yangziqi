"""① 季度财报追踪 + 财报评分 0-100（P1）。

- fetch_quarters(code, n=8): 抓最近 n 个季度财务（主要指标 + 资产负债表合并）
- add_growth: 同比 API 自带；环比取单季 DJD_*_QOQ
- is_accelerating: 营收&净利同比是否连续抬升
- score: 按用户权重输出 0-100 + 明细

评分权重（满分100）：
  营收同比改善 15 / 净利同比改善 20 / 扣非改善 15 / 毛利率改善 10 /
  经营现金流改善 15 / 合同负债增加 10 / 存货健康 10 / 负债率可控 5
"""
from __future__ import annotations

from typing import Dict, List, Optional

import pandas as pd

try:
    pd.set_option("future.infer_string", False)
except Exception:  # noqa: BLE001
    pass

from .. import em_f10


def _num(v) -> Optional[float]:
    try:
        if v is None or v == "":
            return None
        return float(v)
    except (ValueError, TypeError):
        return None


def fetch_quarters(code: str, n: int = 8) -> pd.DataFrame:
    """返回最近 n 季度财务，按报告期升序（旧→新，便于看趋势）。空则返回空 DataFrame。"""
    main = em_f10.report(em_f10.RPT_MAIN, code, page_size=n)
    bal = em_f10.report(em_f10.RPT_BALANCE, code, page_size=n)
    if not main:
        return pd.DataFrame()
    bal_by_date = {str(r.get("REPORT_DATE"))[:10]: r for r in bal}
    rows = []
    for m in main:
        d = str(m.get("REPORT_DATE"))[:10]
        b = bal_by_date.get(d, {})
        rows.append({
            "报告期": m.get("REPORT_DATE_NAME"),
            "报告日": d,
            "营收(亿)": _div(_num(m.get("TOTALOPERATEREVE")), 1e8),
            "营收同比%": _num(m.get("TOTALOPERATEREVETZ")),
            "归母净利(亿)": _div(_num(m.get("PARENTNETPROFIT")), 1e8),
            "归母同比%": _num(m.get("PARENTNETPROFITTZ")),
            "扣非净利(亿)": _div(_num(m.get("KCFJCXSYJLR")), 1e8),
            "扣非同比%": _num(m.get("KCFJCXSYJLRTZ")),
            "毛利率%": _num(m.get("XSMLL")),
            "毛利率同比变动": _num(m.get("XSMLL_TB")),
            "净利率%": _num(m.get("XSJLL")),
            "经营现金流(亿)": _div(_num(m.get("NETCASH_OPERATE_PK")), 1e8),
            "ROE加权%": _num(m.get("ROEJQ")),
            "资产负债率%": _num(m.get("ZCFZL")),
            "单季营收同比%": _num(m.get("DJD_TOI_YOY")),
            "单季营收环比%": _num(m.get("DJD_TOI_QOQ")),
            "单季净利同比%": _num(m.get("DJD_DPNP_YOY")),
            "单季净利环比%": _num(m.get("DJD_DPNP_QOQ")),
            "存货(亿)": _div(_num(b.get("INVENTORY")), 1e8),
            "存货同比%": _num(b.get("INVENTORY_YOY")),
            "应收账款(亿)": _div(_num(b.get("ACCOUNTS_RECE")), 1e8),
            "应收同比%": _num(b.get("ACCOUNTS_RECE_YOY")),
            "合同负债(亿)": _div(_num(b.get("CONTRACT_LIAB")), 1e8),
            "合同负债同比%": _num(b.get("CONTRACT_LIAB_YOY")),
        })
    df = pd.DataFrame(rows).iloc[::-1].reset_index(drop=True)  # 升序
    return df


def _div(v, d):
    return round(v / d, 4) if v is not None else None


def is_accelerating(df: pd.DataFrame) -> Dict:
    """营收&净利同比是否连续抬升（近3季趋势向上）。"""
    if len(df) < 2:
        return {"营收加速": None, "净利加速": None}

    def _trend(col):
        s = [x for x in df[col].tolist() if x is not None][-3:]
        if len(s) < 2:
            return None
        return all(s[i] >= s[i - 1] for i in range(1, len(s)))

    return {"营收加速": _trend("营收同比%"), "净利加速": _trend("归母同比%")}


def _improve(now: Optional[float], prev: Optional[float], full: float) -> tuple:
    """同比类指标评分：同比为正给6成，较上季抬升再给4成。返回(得分, 说明)。"""
    if now is None:
        return 0.0, "N/A"
    s, tag = 0.0, ""
    if now > 0:
        s += full * 0.6
        tag = f"同比+{now:.0f}%"
    else:
        tag = f"同比{now:.0f}%"
    if prev is not None and now > prev:
        s += full * 0.4
        tag += "·加速"
    elif prev is not None and now <= prev and now > 0:
        tag += "·放缓"
    return round(min(s, full), 1), tag


def score(df: pd.DataFrame) -> Dict:
    """财报评分 0-100 + 明细。需要 fetch_quarters 的 df（升序）。"""
    if df is None or df.empty:
        return {"score": None, "breakdown": {}, "note": "无财务数据"}
    cur = df.iloc[-1]
    prev = df.iloc[-2] if len(df) > 1 else None

    def g(row, col):
        return None if row is None else (None if pd.isna(row[col]) else float(row[col]))

    bd = {}
    # 1 营收同比改善 15
    bd["营收同比改善"] = (*_improve(g(cur, "营收同比%"), g(prev, "营收同比%"), 15), 15)
    # 2 净利同比改善 20
    bd["净利同比改善"] = (*_improve(g(cur, "归母同比%"), g(prev, "归母同比%"), 20), 20)
    # 3 扣非改善 15
    bd["扣非同比改善"] = (*_improve(g(cur, "扣非同比%"), g(prev, "扣非同比%"), 15), 15)
    # 4 毛利率改善 10 （毛利率同比变动>0）
    mll_tb = g(cur, "毛利率同比变动")
    if mll_tb is None:
        bd["毛利率改善"] = (0.0, "N/A", 10)
    elif mll_tb > 0:
        bd["毛利率改善"] = (10.0, f"毛利率同比+{mll_tb:.1f}pct", 10)
    else:
        bd["毛利率改善"] = (round(max(0.0, 10 + mll_tb), 1), f"毛利率同比{mll_tb:.1f}pct", 10)
    # 5 经营现金流改善 15 （为正给主分 + 较上季改善）
    cf, cfp = g(cur, "经营现金流(亿)"), g(prev, "经营现金流(亿)")
    if cf is None:
        bd["现金流改善"] = (0.0, "N/A", 15)
    else:
        s = 15 * 0.6 if cf > 0 else 0.0
        tag = f"经营现金流{cf:.2f}亿"
        if cfp is not None and cf > cfp:
            s += 15 * 0.4
            tag += "·改善"
        bd["现金流改善"] = (round(min(s, 15), 1), tag, 15)
    # 6 合同负债增加 10
    cl = g(cur, "合同负债同比%")
    if cl is None:
        bd["合同负债增加"] = (0.0, "N/A", 10)
    elif cl > 0:
        bd["合同负债增加"] = (10.0, f"合同负债同比+{cl:.0f}%", 10)
    else:
        bd["合同负债增加"] = (round(max(0.0, 10 + cl / 10), 1), f"合同负债同比{cl:.0f}%", 10)
    # 7 存货健康 10 （存货增速不超营收增速太多）
    inv, rev = g(cur, "存货同比%"), g(cur, "营收同比%")
    if inv is None:
        bd["存货健康"] = (5.0, "N/A(中性)", 10)
    elif rev is not None and inv <= rev + 10:
        bd["存货健康"] = (10.0, f"存货同比{inv:.0f}%≤营收+10pct", 10)
    elif inv <= 20:
        bd["存货健康"] = (7.0, f"存货同比{inv:.0f}%温和", 10)
    else:
        bd["存货健康"] = (3.0, f"存货同比{inv:.0f}%偏高", 10)
    # 8 负债率可控 5
    zcfz = g(cur, "资产负债率%")
    if zcfz is None:
        bd["负债率可控"] = (2.5, "N/A", 5)
    elif zcfz < 50:
        bd["负债率可控"] = (5.0, f"负债率{zcfz:.0f}%", 5)
    elif zcfz < 60:
        bd["负债率可控"] = (3.5, f"负债率{zcfz:.0f}%", 5)
    elif zcfz < 70:
        bd["负债率可控"] = (2.0, f"负债率{zcfz:.0f}%", 5)
    else:
        bd["负债率可控"] = (0.0, f"负债率{zcfz:.0f}%偏高", 5)

    total = round(sum(v[0] for v in bd.values()), 1)
    return {"score": total, "period": cur["报告期"], "breakdown": bd,
            "accel": is_accelerating(df)}


def report_md(code: str, name: str = "", n: int = 8) -> str:
    """便捷：直接输出该股财报追踪+评分的 Markdown。"""
    df = fetch_quarters(code, n)
    if df.empty:
        return f"### 📊 {name} {code} 财报追踪\n> 无法获取财务数据（东财限流/代码异常）"
    sc = score(df)
    cols = ["报告期", "营收(亿)", "营收同比%", "归母净利(亿)", "归母同比%",
            "扣非同比%", "毛利率%", "经营现金流(亿)", "合同负债同比%", "ROE加权%", "资产负债率%"]
    show = df[cols].tail(6)
    lines = [f"### 📊 {name} {code} 财报追踪（近{len(show)}季）",
             f"**财报评分：{sc['score']}/100**　最新：{sc['period']}　"
             f"营收加速={sc['accel']['营收加速']} 净利加速={sc['accel']['净利加速']}", "",
             "| " + " | ".join(cols) + " |",
             "|" + "---|" * len(cols)]
    for _, r in show.iterrows():
        lines.append("| " + " | ".join(
            ("" if pd.isna(r[c]) else (f"{r[c]:.2f}" if isinstance(r[c], float) else str(r[c])))
            for c in cols) + " |")
    lines.append("\n**评分明细：**")
    for k, (pts, tag, mx) in sc["breakdown"].items():
        lines.append(f"- {k}：{pts}/{mx}　（{tag}）")
    return "\n".join(lines)
