"""③ 同行对比 / 估值性价比（P2）。

数据源：东财 F10 估值表 RPT_VALUEANALYSIS_DET（含 PE/PB/PS/PEG/市值 + BOARD_CODE 行业）
+ 主要指标 RPT_F10_FINANCE_MAINFINADATA（营收/净利增速/ROE/毛利率）+ em_fetch 日线（20/60日涨幅）。

- valuation(code): 单只估值 + 所属行业
- compare(code, top): 同行业按流通市值取 top，补增长/涨幅，输出对比表
- rank_value(df): 性价比排名（低估+高增+不弱）
"""
from __future__ import annotations

from typing import Dict, List, Optional

import pandas as pd

try:
    pd.set_option("future.infer_string", False)
except Exception:  # noqa: BLE001
    pass

from .. import em_f10

_VAL = "RPT_VALUEANALYSIS_DET"


def _f(v) -> Optional[float]:
    try:
        return None if v in (None, "", "-") else float(v)
    except (ValueError, TypeError):
        return None


def valuation(code: str) -> Dict:
    """单只最新估值 + 行业。"""
    rows = em_f10.report(_VAL, code, page_size=1, sort_col="TRADE_DATE")
    if not rows:
        return {}
    r = rows[0]
    return {
        "代码": r.get("SECURITY_CODE"), "名称": r.get("SECURITY_NAME_ABBR"),
        "交易日": str(r.get("TRADE_DATE"))[:10],
        "收盘": _f(r.get("CLOSE_PRICE")), "当日涨幅%": _f(r.get("CHANGE_RATE")),
        "PE_TTM": _f(r.get("PE_TTM")), "PE静": _f(r.get("PE_LAR")),
        "PB": _f(r.get("PB_MRQ")), "PS": _f(r.get("PS_TTM")), "PEG": _f(r.get("PEG_CAR")),
        "总市值(亿)": _div(_f(r.get("TOTAL_MARKET_CAP")), 1e8),
        "流通市值(亿)": _div(_f(r.get("NOTLIMITED_MARKETCAP_A")), 1e8),
        "BOARD_CODE": r.get("BOARD_CODE"), "行业": r.get("BOARD_NAME"),
    }


def _div(v, d):
    return round(v / d, 2) if v is not None else None


def _growth(code: str) -> Dict:
    """单只最新季 营收/净利同比、ROE、毛利率。"""
    rows = em_f10.report(em_f10.RPT_MAIN, code, page_size=1)
    if not rows:
        return {}
    r = rows[0]
    return {"营收增速%": _f(r.get("TOTALOPERATEREVETZ")), "净利增速%": _f(r.get("PARENTNETPROFITTZ")),
            "ROE%": _f(r.get("ROEJQ")), "毛利率%": _f(r.get("XSMLL"))}


def _chg_20_60(code: str) -> Dict:
    """近20/60日涨幅（em_fetch 日线；失败返回 None）。"""
    try:
        from .. import em_fetch
        d = em_fetch.daily(code)
        if d is None or len(d) < 61:
            return {"20日%": None, "60日%": None}
        c = float(d.iloc[-1]["close"])
        c20 = float(d.iloc[-21]["close"]); c60 = float(d.iloc[-61]["close"])
        return {"20日%": round((c / c20 - 1) * 100, 1), "60日%": round((c / c60 - 1) * 100, 1)}
    except Exception:  # noqa: BLE001
        return {"20日%": None, "60日%": None}


def compare(code: str, top: int = 6, with_kline: bool = True) -> pd.DataFrame:
    """同行业按流通市值取 top 家（含目标），补增长/涨幅。返回对比 DataFrame。"""
    v = valuation(code)
    if not v or not v.get("BOARD_CODE"):
        return pd.DataFrame()
    board, date = v["BOARD_CODE"], v["交易日"]
    rows = em_f10.query(_VAL, f'(BOARD_CODE="{board}")(TRADE_DATE=\'{date}\')',
                        page_size=80, sort_col="TOTAL_MARKET_CAP")
    # 目标股优先并入（小市值目标常排在行业 80 名外、不在 board 返回里→显式补拉）
    target_row = next((r for r in rows if str(r.get("SECURITY_CODE")) == str(code)), None)
    if target_row is None:
        tr_raw = em_f10.report(_VAL, code, page_size=1, sort_col="TRADE_DATE")
        target_row = tr_raw[0] if tr_raw else None
    picked = [target_row] if target_row else []
    seen = {str(code)} if target_row else set()
    for r in rows:
        c = str(r.get("SECURITY_CODE"))
        if c and c not in seen:
            picked.append(r); seen.add(c)
        if len(picked) >= top:
            break
    out = []
    for r in picked:
        c = r.get("SECURITY_CODE")
        g = _growth(c)
        k = _chg_20_60(c) if with_kline else {"20日%": None, "60日%": None}
        out.append({
            "代码": c, "名称": r.get("SECURITY_NAME_ABBR"),
            "PE_TTM": _f(r.get("PE_TTM")), "PB": _f(r.get("PB_MRQ")),
            "PS": _f(r.get("PS_TTM")), "PEG": _f(r.get("PEG_CAR")),
            "总市值(亿)": _div(_f(r.get("TOTAL_MARKET_CAP")), 1e8),
            "营收增速%": g.get("营收增速%"), "净利增速%": g.get("净利增速%"),
            "ROE%": g.get("ROE%"), "毛利率%": g.get("毛利率%"),
            "20日%": k.get("20日%"), "60日%": k.get("60日%"),
            "_是目标": c == code,
        })
    return pd.DataFrame(out)


def rank_value(df: pd.DataFrame) -> pd.DataFrame:
    """性价比排名：净利增速高 + PE/PEG低 + ROE高 → 综合分。"""
    if df.empty:
        return df
    d = df.copy()

    def _hi(col):  # 越高越好 → 升序rank: 最大值得最高pct
        s = pd.to_numeric(d[col], errors="coerce")
        return s.rank(ascending=True, pct=True).fillna(0.3)

    # 低PE好(仅正PE参与;负PE=无盈利给低分0.15)、高净利增速/ROE/营收增速好
    pe = pd.to_numeric(d["PE_TTM"], errors="coerce")
    pe_score = pe.where(pe > 0).rank(ascending=False, pct=True).fillna(0.15)
    score = (pe_score * 0.25 + _hi("净利增速%") * 0.35
             + _hi("ROE%") * 0.25 + _hi("营收增速%") * 0.15)
    d["性价比分"] = (score * 100).round(1)
    return d.sort_values("性价比分", ascending=False).reset_index(drop=True)


def report_md(code: str, name: str = "", top: int = 6) -> str:
    df = compare(code, top=top)
    if df.empty:
        return f"### ⚖️ {name} {code} 同行对比\n> 无法获取估值/行业数据"
    ranked = rank_value(df)
    v = valuation(code)
    tgt_rank = ranked.index[ranked["代码"] == code].tolist()
    rk = (tgt_rank[0] + 1) if tgt_rank else "—"
    cols = ["名称", "PE_TTM", "PB", "PS", "PEG", "营收增速%", "净利增速%", "ROE%", "毛利率%", "20日%", "60日%", "性价比分"]
    lines = [f"### ⚖️ {name} {code} 同行对比（{v.get('行业')}｜性价比排名 **第{rk}/{len(ranked)}**）",
             "| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    for _, r in ranked.iterrows():
        mark = "**" if r["代码"] == code else ""
        cells = []
        for c in cols:
            val = r[c]
            cells.append("" if pd.isna(val) else (f"{val:.1f}" if isinstance(val, float) else str(val)))
        lines.append("| " + mark + cells[0] + mark + " | " + " | ".join(cells[1:]) + " |")
    return "\n".join(lines)
