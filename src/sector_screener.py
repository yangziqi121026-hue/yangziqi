"""板块池选股引擎。

在预设“板块观察池”内，逐只用真实日线（新浪 stock_zh_a_daily，含换手/流通股本，
单接口即可算 换手率/量比/流通市值）套用 ScreenConfig 的超卖短线标准筛选。

相比全市场扫描：不依赖东财全市场快照（弱网下常失败），以“板块池”为范围，
逐只 K 线稳定可得；并自动算出入场/止损/目标/盈亏比。

所有网络调用异常兜底；不构成投资建议。
"""

from datetime import datetime
from typing import Callable, Dict, List, Optional

import pandas as pd

from . import indicators
from .screener import ScreenConfig

try:
    pd.set_option("future.infer_string", False)
except Exception:  # noqa: BLE001
    pass

# ----------------------------------------------------------------------------
# 预设板块观察池（code -> name）。可自行增删。
# ----------------------------------------------------------------------------
POOLS: Dict[str, Dict[str, str]] = {
    "电力": {
        "600900": "长江电力", "600011": "华能国际", "600795": "国电电力",
        "600027": "华电国际", "601985": "中国核电", "003816": "中国广核",
        "600905": "三峡能源", "001289": "龙源电力", "600674": "川投能源",
        "600886": "国投电力", "600023": "浙能电力", "000543": "皖能电力",
        "600642": "申能股份", "600863": "内蒙华电", "601991": "大唐发电",
        "600021": "上海电力", "000539": "粤电力A", "601016": "节能风电",
    },
    "AI算力/服务器": {
        "601138": "工业富联", "000977": "浪潮信息", "000938": "紫光股份",
        "603019": "中科曙光", "000034": "神州数码", "002261": "拓维信息",
        "688041": "海光信息", "688256": "寒武纪", "300474": "景嘉微",
        "301236": "软通动力", "600498": "烽火通信", "002929": "润建股份",
        "603881": "数据港", "300846": "首都在线", "603629": "利通电子",
        "000628": "高新发展", "600602": "云赛智联", "002229": "鸿博股份",
    },
    "光模块/CPO": {
        "300308": "中际旭创", "300502": "新易盛", "300394": "天孚通信",
        "300570": "太辰光", "603083": "剑桥科技", "688498": "源杰科技",
        "002281": "光迅科技", "300548": "博创科技", "688313": "仕佳光子",
        "000988": "华工科技", "688205": "德科立", "301205": "联特科技",
        "688048": "长光华芯", "300757": "罗博特科", "300620": "光库科技",
        "002902": "铭普光磁", "301486": "致尚科技", "002384": "东山精密",
    },
    "半导体": {
        "002371": "北方华创", "688012": "中微公司", "603986": "兆易创新",
        "688981": "中芯国际", "688008": "澜起科技", "603501": "韦尔股份",
        "688126": "沪硅产业", "688396": "华润微", "002049": "紫光国微",
        "688082": "盛美上海", "300661": "圣邦股份", "300782": "卓胜微",
        "688200": "华峰测控", "688521": "芯原股份", "688525": "佰维存储",
        "688041": "海光信息",
    },
    "机器人": {
        "002472": "双环传动", "688017": "绿的谐波", "002747": "埃斯顿",
        "300124": "汇川技术", "002896": "中大力德", "300607": "拓斯达",
        "002527": "新时达", "003021": "兆威机电", "603728": "鸣志电器",
        "300161": "华中数控", "688322": "奥比中光", "301029": "怡合达",
    },
    "新能源/锂电": {
        "300750": "宁德时代", "002594": "比亚迪", "300014": "亿纬锂能",
        "002460": "赣锋锂业", "002466": "天齐锂业", "300274": "阳光电源",
        "601012": "隆基绿能", "688599": "天合光能", "002129": "TCL中环",
        "300450": "先导智能", "002709": "天赐材料", "300073": "当升科技",
        "002812": "恩捷股份", "605117": "德业股份", "601877": "正泰电器",
    },
}


def list_sectors() -> List[str]:
    return list(POOLS.keys())


def _sina_symbol(code: str) -> str:
    c = str(code).strip()
    prefix = "sh" if c[0] == "6" else ("sz" if c[0] in "03" else "bj")
    return prefix + c


def _fetch(code: str) -> Optional[pd.DataFrame]:
    """用新浪日线拉前复权K线（含 turnover / outstanding_share）。失败返回 None。"""
    try:
        import akshare as ak

        d = ak.stock_zh_a_daily(symbol=_sina_symbol(code), adjust="qfq")
        if d is None or len(d) < 60:
            return None
        d["date"] = pd.to_datetime(d["date"], errors="coerce").astype(str).str[:10]
        return d
    except Exception:  # noqa: BLE001
        return None


def _check(code: str, name: str, sector: str, d: pd.DataFrame, cfg: ScreenConfig) -> dict:
    """对单只票算指标并套规则，返回展示行（含 pass/fails；通过则含价位）。"""
    d = indicators.compute_all(d).reset_index(drop=True)
    r = d.iloc[-1]
    close = float(r["close"])
    ma5, ma10, ma20, ma60 = float(r.MA5), float(r.MA10), float(r.MA20), float(r.MA60)
    rsi = float(r.RSI14)

    hist = d["MACD_Hist"].dropna()
    h1 = float(hist.iloc[-1]); h0 = float(hist.iloc[-2]) if len(hist) > 1 else h1
    just_red = h1 > 0 and h0 <= 0
    green_shrink = h1 < 0 and h1 > h0
    macd_state = "刚翻红" if just_red else ("绿柱缩短" if green_shrink else ("红柱放大" if h1 > 0 else "绿柱放大"))

    low52 = float(d["low"].tail(250).min())
    high20 = float(d["high"].tail(20).max())
    low5 = float(d["low"].tail(5).min())
    chg20 = (close / float(d["close"].iloc[-21]) - 1) * 100 if len(d) > 21 else 0.0
    dist52 = (close / low52 - 1) * 100 if low52 > 0 else -1
    prev5_vol = float(d["volume"].iloc[-6:-1].mean()) if len(d) > 6 else float(r["volume"])
    volr = float(r["volume"]) / prev5_vol if prev5_vol else None
    turn = float(r["turnover"]) * 100 if "turnover" in d.columns else None
    fcap = float(r["outstanding_share"]) * close / 1e8 if "outstanding_share" in d.columns else None

    fails: List[str] = []
    if not (cfg.rsi_min <= rsi <= cfg.rsi_max):
        fails.append(f"RSI{rsi:.0f}")
    if cfg.require_above_ma5 and close < ma5:
        fails.append("未站上MA5")
    if cfg.require_above_ma10 and close < ma10:
        fails.append("未站上MA10")
    if cfg.require_above_ma20 and close < ma20:
        fails.append("未站上MA20")
    if not (cfg.dist52_low_min_pct <= dist52 <= cfg.dist52_low_max_pct):
        fails.append(f"距52低{dist52:.0f}%")
    if not (cfg.chg20_min_pct <= chg20 <= cfg.chg20_max_pct):
        fails.append(f"近20日{chg20:.0f}%")
    if cfg.require_macd_reversal and not (just_red or green_shrink):
        fails.append("MACD未反转")
    if turn is None or not (cfg.turnover_min <= turn <= cfg.turnover_max):
        fails.append(f"换手{turn:.1f}%" if turn is not None else "换手NA")
    if volr is None or volr <= cfg.vol_ratio_min:
        fails.append(f"量比{volr:.1f}" if volr is not None else "量比NA")

    row = {
        "code": code, "name": name, "theme": sector, "price": round(close, 2),
        "rsi": round(rsi, 1), "macd_state": macd_state,
        "ma5": round(ma5, 2), "ma10": round(ma10, 2), "ma20": round(ma20, 2), "ma60": round(ma60, 2),
        "dist_52w_low_pct": round(dist52, 1), "chg20": round(chg20, 2),
        "turnover": round(turn, 2) if turn is not None else None,
        "vol_ratio": round(volr, 2) if volr is not None else None,
        "float_cap_yi": round(fcap, 0) if fcap else None,
        "fund_status": "板块池/需核验", "fails": fails, "pass": len(fails) == 0,
    }

    # 价位与盈亏比（无论是否通过都算，供展示/触发参考）
    entry_low = round(min(ma5, ma10), 2)
    entry_high = round(max(ma5, ma10), 2)
    entry_mid = (entry_low + entry_high) / 2
    stop = round(min(ma10 * 0.99, low5), 2)
    if stop >= entry_mid:
        stop = round(entry_mid * 0.97, 2)
    target = round(max(high20, entry_mid * 1.05), 2)
    risk = entry_mid - stop
    rr = round((target - entry_mid) / risk, 2) if risk > 0 else 0
    row.update({
        "entry_low": entry_low, "entry_high": entry_high,
        "stop": stop, "target": target, "rr": rr,
        "first_position": "2成" if rr >= 2.5 else "1成",
        "add_condition": f"放量站稳 {entry_high} 上方且量比>{cfg.vol_ratio_min}，加 1 成",
        "logic": (f"RSI{rsi:.0f}｜MACD {macd_state}｜距52低{dist52:.0f}%｜近20日{chg20:.1f}%｜"
                  f"换手{turn:.1f}%｜板块：{sector}" if turn is not None else f"RSI{rsi:.0f}｜{sector}"),
        "score": round(rr * (volr or 1), 2),
    })
    # 盈亏比不达标也算未通过
    if row["pass"] and rr < cfg.min_rr:
        row["pass"] = False
        row["fails"].append(f"盈亏比{rr}")
    return row


def screen_pool(sector: str, cfg: Optional[ScreenConfig] = None,
                progress_callback: Optional[Callable[[str, float], None]] = None) -> Dict:
    """筛选指定板块池，返回 {sector, rows, candidates, meta}。"""
    cfg = cfg or ScreenConfig()
    pool = POOLS.get(sector, {})
    meta = {"data_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "sector": sector, "count": len(pool), "fetched": 0, "errors": []}

    rows: List[dict] = []
    n = max(len(pool), 1)
    for i, (code, name) in enumerate(pool.items()):
        if progress_callback:
            progress_callback(f"拉取 {i+1}/{len(pool)}：{name}", (i + 1) / n)
        d = _fetch(code)
        if d is None:
            meta["errors"].append(f"{code} {name} 拉取失败")
            continue
        meta["fetched"] += 1
        try:
            rows.append(_check(code, name, sector, d, cfg))
        except Exception as exc:  # noqa: BLE001
            meta["errors"].append(f"{code} {name} 计算异常:{exc}")

    candidates = sorted([r for r in rows if r["pass"]], key=lambda x: x["score"], reverse=True)
    rows.sort(key=lambda x: (not x["pass"], -x["score"]))
    return {"sector": sector, "rows": rows, "candidates": candidates, "meta": meta}
