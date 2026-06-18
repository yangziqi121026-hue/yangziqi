"""收盘后『明日短线候选 + 深度分析』流水线。

流程：
  1. 拉一次隔夜美股 + 美国新闻（外围定调，全篇只拉一次）。
  2. 扫描候选池：分层观察池(daily_watch.WATCHLIST) + 板块池(sector_screener.POOLS，
     电力/算力/光模块/半导体/机器人/新能源 共~100只)，新浪日线、线程池并发(~80秒)。
  3. 按用户铁律给候选打分排名：必须站上MA5、非破位、非超卖禁买、市值20-500亿、
     RSI<70、RR>=1.5；信号优先级 放量突破>回踩到位>站上MA5。
  4. 对 Top-N 候选逐只做 stock_deepdive 深度分析（外围只在顶部出现一次）。
  5. 输出合并报告 reports/明日候选_YYYYMMDD.md。

外围逆风(risk-off)日会自动提示降仓；若无一只满足四重共振 → 诚实给『今日无主推、只列观察池+防御』。
个股主力/北向资金本环境取不到 → 资金面降权。不构成投资建议；所有买点配破 MA5 硬止损。
"""

import os
from datetime import datetime
from typing import Dict, List

import pandas as pd

from . import daily_watch, review_log, sector_screener, stock_deepdive

try:
    pd.set_option("future.infer_string", False)
except Exception:  # noqa: BLE001
    pass

_BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_REPORTS = os.path.join(_BASE, "reports")

_SIG_RANK = {"✅放量突破/多头": 3, "🟢回踩低吸位(缩量)": 2, "⚪站上MA5·观望": 1}


def _universe(wide: bool = True) -> Dict[str, tuple]:
    """合并候选池：分层观察池(daily_watch) +（wide 时）板块池(sector_screener)。

    返回 {code: (tier, name)}；分层观察池的 tier 优先（不被板块池覆盖）。
    """
    uni: Dict[str, tuple] = {}
    for tier, d in daily_watch.WATCHLIST.items():
        for c, n in d.items():
            uni[c] = (tier, n)
    if wide:
        for sector, d in sector_screener.POOLS.items():
            tier = "防御·电力" if sector == "电力" else f"板块·{sector}"
            for c, n in d.items():
                uni.setdefault(c, (tier, n))  # 不覆盖观察池已有分层
    return uni


def _scan_one(args):
    code, tier, name = args
    d = daily_watch._fetch(code, retries=2)
    if d is None:
        return ("fail", f"{code}{name}")
    try:
        return ("ok", daily_watch._classify(code, name, tier, d))
    except Exception as exc:  # noqa: BLE001
        return ("fail", f"{code}{name}(算错:{exc})")


def _scan_universe(uni: Dict[str, tuple], max_workers: int = 8):
    """并发拉新浪日线 + 套 daily_watch 分类规则。返回 (rows, fails)。

    并发(线程池)把 ~100 只的扫描从数分钟压到数十秒；新浪日线接口可承受。
    """
    from concurrent.futures import ThreadPoolExecutor

    rows: List[Dict] = []
    fails: List[str] = []
    items = [(c, t, n) for c, (t, n) in uni.items()]
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        for status, payload in ex.map(_scan_one, items):
            if status == "ok":
                rows.append(payload)
            else:
                fails.append(payload)
    return rows, fails


def _eligible(r: Dict) -> bool:
    """是否够格做『明日短线候选』（用户铁律硬门槛）。"""
    return (
        r.get("above5", r["close"] >= r["ma5"])
        and "破位" not in r["signal"]
        and "超卖" not in r["signal"]
        and r["cap_ok"]
        and r["rsi"] < 70
        and r["rr"] is not None and r["rr"] >= 1.5
        and r["signal"] in _SIG_RANK
    )


def _confirmed(r: Dict) -> bool:
    """量价确认 = 放量(量比>1.3) 且 站上 MA10。这是发奖牌的唯一门槛。"""
    return (r["close"] >= r["ma10"]) and ((r.get("volr") or 0) > 1.3)


def _score(r: Dict) -> float:
    """纯量价排序，禁止主观题材加权：
    ① 放量站MA10(已确认) 最高优先 → ② 站上MA10 → ③ 信号等级 → ④ RR → ⑤ 量比。
    """
    above10 = r["close"] >= r["ma10"]
    return ((1_000_000 if _confirmed(r) else 0)
            + (100_000 if above10 else 0)
            + _SIG_RANK.get(r["signal"], 0) * 1000
            + min(r["rr"] or 0, 5) * 100
            + (r["volr"] or 0) * 10)


def generate(top_n: int = 3, save: bool = True, wide: bool = True,
             max_workers: int = 6) -> str:
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    # 1. 外围（只拉一次）
    us = stock_deepdive._us_env()
    fnews = stock_deepdive._foreign_news()

    # 2. 扫描候选池（wide=True 时并入板块池 ~100 只）
    uni = _universe(wide=wide)
    rows, fails = _scan_universe(uni, max_workers=max_workers)
    m = {"scanned": len(rows), "total": len(uni), "fails": fails}
    # 名称映射（供深度分析用，绕过取不到的名称接口）
    name_map = {c: nm for c, (_t, nm) in uni.items()}

    # 3. 排名（纯量价）+ 发奖牌（仅"放量站MA10已确认"者可得🥇🥈🥉，其余一律⚠️）
    # ⛔ 防御板块(电力/红利)剔除出"放量突破发奖牌"排名——它们放量常是利空/出货而非突破
    #    (教训：粤电力A 量比2.06"放量站MA10"给🥈，次日-9.98%跌停)。防御只做回踩打底。
    cands = sorted([r for r in rows if _eligible(r) and not r["tier"].startswith("防御")],
                   key=_score, reverse=True)
    mi = 0
    for r in cands:
        if _confirmed(r) and mi < 3:
            r["medal"] = ["🥇", "🥈", "🥉"][mi]; mi += 1
        else:
            r["medal"] = "⚠️"
    defensive = [r for r in rows if r["tier"].startswith("防御")]
    watch = [r for r in rows if (not _eligible(r)) and "破位" not in r["signal"]
             and not r["tier"].startswith("防御")]

    # 复盘日志：先评估历史未结记录(用今日最新数据)，再把今日候选落库
    try:
        review_log.evaluate()
    except Exception:  # noqa: BLE001
        pass

    env_bad = (us["nasdaq"] is not None and us["nasdaq"] <= -1.0) or \
              (us["sox"] is not None and us["sox"] <= -1.5)
    pos_cap = "≤2成（外围逆风）" if env_bad else "≤3成"

    L: List[str] = [f"# 明日短线候选 + 深度分析（收盘后定稿）", f"_{now}_", ""]

    # 〇 外围（一次）
    L.append("## 〇、外围环境（隔夜美股 + 美国新闻）")
    L.append(f"**定调：{us['tone']}** — {us['tone_note']}　**今日建议总仓位上限：{pos_cap}**")
    L.append("")
    L.append("**隔夜美股：** " + "｜".join(
        f"{x['name']} {x['close'] if x['close'] is not None else 'NA'}"
        + (f"({stock_deepdive._fmt(x['chg'])})" if x["chg"] is not None else "") for x in us["idx"]))
    L.append("")
    L.append("**科技龙头：** " + "｜".join(
        f"{x['name']} {stock_deepdive._fmt(x['chg'])}" for x in us["leaders"] if x["chg"] is not None))
    L.append("")
    L.append("**美国/地缘新闻：**")
    L += fnews
    L.append("")

    # 一 候选排名
    fail_note = f"｜失败 {len(m['fails'])}" if m["fails"] else ""
    L.append(f"## 一、明日短线候选排名（达标 {len(cands)} 只 / 扫描 {m['scanned']}/{m['total']}{fail_note}）")
    L.append("> 排序=纯量价（放量站MA10优先），**禁主观题材加权**；**🥇🥈🥉仅授予『放量站MA10已确认』者，未确认一律⚠️**；"
             "**防御板块(电力/红利)不参与发奖牌、只在下方做回踩打底**（其放量多为利空/出货，非突破）。")
    if not cands:
        L.append("**⚠️ 今日无一只满足门槛（站MA5+放量/回踩到位+RR≥1.5+市值合规+非超买）。**")
        L.append("**纪律结论：明日无【主推】，空仓或只做防御。** 宁可错过，不碰不达标的票。")
    else:
        L.append("| 奖牌 | 代码 | 名称 | 层 | 信号 | 现价 | RSI | 量比 | RR | 市值 | 入场 | 止损 | 目标 |")
        L.append("|---|---|---|---|---|---|---|---|---|---|---|---|---|")
        for r in cands:
            conf = "✅放量站MA10" if _confirmed(r) else ("站MA10未放量" if r["close"] >= r["ma10"] else "仅站MA5")
            L.append(f"| {r['medal']} | {r['code']} | {r['name']} | {r['tier']} | {r['signal']}/{conf} | {r['close']} | "
                     f"{r['rsi']} | {r['volr']} | {r['rr']} | {r['cap']}亿 | {r['entry']} | {r['stop']} | {r['target']} |")
    L.append("")

    # 落库今日候选（含防御/观察池一并记录，便于全口径复盘）
    try:
        review_log.log_picks(cands, tone=us["tone"])
    except Exception:  # noqa: BLE001
        pass

    # 二 Top-N 深度分析
    if cands:
        picks = cands[:top_n]
        L.append(f"## 二、Top-{len(picks)} 深度分析（外围见上，逐只技术+DeepSeek）")
        L.append("")
        for r in picks:
            try:
                sub = stock_deepdive.analyze(
                    r["code"], name=name_map.get(r["code"], r["name"]),
                    theme=r["tier"], fund="—", save=False,
                    us=us, fnews=fnews, include_env=False, heading="###")
                L.append(sub)
                L.append("\n---\n")
            except Exception as exc:  # noqa: BLE001
                L.append(f"### {r['code']} {r['name']} 深度分析失败：{exc}\n")

    # 三 防御 + 观察池（宽池下只列站上MA5的、并限量，避免刷屏）
    defensive = [r for r in defensive if r["close"] >= r["ma5"]]
    if defensive:
        L.append(f"## 三、防御打底（站MA5，外围逆风可避风｜共{len(defensive)}只，列前8）")
        for r in defensive[:8]:
            L.append(f"- {r['code']} {r['name']}｜收{r['close']}｜RSI{r['rsi']}｜{r['macd']}｜"
                     f"MA5 {r['ma5']}｜量比{r['volr']}｜{r['signal']}")
        L.append("")
    # 观察池：站上MA5但未达标的，按接近放量/RR 排序，列前12
    watch = sorted([r for r in watch if r["close"] >= r["ma5"]],
                   key=lambda r: ((r["rr"] or 0), (r["volr"] or 0)), reverse=True)
    if watch:
        L.append(f"## 四、观察池（站MA5未达标，等放量/共振｜共{len(watch)}只，列前12）")
        for r in watch[:12]:
            L.append(f"- {r['code']} {r['name']}（{r['tier']}）｜收{r['close']}｜{r['signal']}｜"
                     f"量比{r['volr']}｜RR{r['rr']}｜距MA5 {round((r['close']/r['ma5']-1)*100,1)}%")
        L.append("")

    # 五 复盘成绩单（用历史推荐 vs 真实走势，量化约束分析者）
    try:
        L.append("## 五、复盘成绩单（推荐 vs 真实走势·自动累计）")
        L.append(review_log.scorecard_md())
        L.append("> 口径：推荐日收盘→下一交易日收盘的方向；单独统计破止损率。胜率低/止损率高=该收敛。")
        L.append("")
    except Exception:  # noqa: BLE001
        pass

    # 纪律
    L.append("## 纪律与仓位")
    L.append(f"- 今日外围：{us['tone']}；**总仓位上限 {pos_cap}**，单只首仓1成、科创板减半。")
    L.append("- 只做达标候选：站上MA5+量比>1.3放量或回踩缩量到位+RR≥1.5+市值20-500亿+RSI<70。")
    L.append("- **买点全部配破 MA5 硬止损**；破位/超卖一律禁买。")
    L.append("- ⛔ **外围只调总仓位上限（逆风≤2成/顺风≤3成），严禁用外围给板块定方向或规避某板块**；"
             "板块方向只看A股自身量价（量比+站MA10）。（教训：拿外围猜板块方向，6/12押半导体涨实跌、6/17躲半导体跌实涨，两次都错）")
    L.append("- 资金面（主力/北向）本环境取不到、为降权估计；消息面需开盘再核验当日异动。")
    L.append("> 本报告由收盘后自动流水线生成，仅供研究，不构成投资建议。")

    report = "\n".join(L)
    if save:
        os.makedirs(_REPORTS, exist_ok=True)
        path = os.path.join(_REPORTS, f"明日候选_{datetime.now().strftime('%Y%m%d')}.md")
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(report)
            print(f"[tomorrow_picks] 已保存：{path}")
        except Exception as exc:  # noqa: BLE001
            print(f"[tomorrow_picks] 保存失败：{exc}")
    return report


if __name__ == "__main__":
    print(generate())
