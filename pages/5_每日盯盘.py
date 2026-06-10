"""每日盯盘 Dashboard：分层池一键扫描 → 分类清单 + 信号提醒 + 导出报告。

逻辑在 src/daily_watch.py。资金面（个股主力/北向）取不到、已降权。
不构成投资建议；所有买点配破 MA5 硬止损。
"""

import os
import sys

import pandas as pd
import streamlit as st

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from src import daily_watch as dw  # noqa: E402

st.set_page_config(page_title="每日盯盘", page_icon="🛰️", layout="wide")
st.title("🛰️ 每日盯盘 · 分层池信号扫描")
st.caption("主线/算力二线/防御/超跌埋伏 一键扫描 ｜ 自动分类+信号提醒+破MA5止损 ｜ 不构成投资建议")

with st.sidebar:
    st.header("⚙️ 盯盘")
    st.write(f"观察池：{sum(len(v) for v in dw.WATCHLIST.values())} 只 / {len(dw.WATCHLIST)} 层")
    for tier, d in dw.WATCHLIST.items():
        st.caption(f"· {tier}：{len(d)} 只")
    run = st.button("🛰️ 开始盯盘扫描", type="primary", use_container_width=True)
    st.caption("逐只拉真实日线，约 30-60 秒；网络差时部分会失败并标注。")

st.warning("⚠️ 数据来自 AKShare 实时接口；**个股主力/北向资金取不到，资金面已降权**（用量比/换手代理）。"
           "本工具仅供研究，不构成投资建议。所有买点配破 MA5 硬止损。")

if run:
    prog = st.progress(0.0, text="开始…")
    try:
        st.session_state["watch"] = dw.scan_watchlist(
            progress_callback=lambda msg, f: prog.progress(min(max(f, 0.0), 1.0), text=msg))
    except Exception as exc:  # noqa: BLE001
        st.error(f"扫描出错：{exc}")
    prog.empty()

res = st.session_state.get("watch")
if not res:
    st.info("点左侧「开始盯盘扫描」生成当日分层清单。")
    st.stop()

m = res["meta"]
st.caption(f"⏱ {m['time']}｜扫描 {m['scanned']}/{m['total']}"
           + (f"｜失败 {len(m['fails'])}：{', '.join(m['fails'])}" if m["fails"] else ""))

# 信号提醒
st.header("🚨 今日信号提醒")
if not res["alerts"]:
    st.info("今日无放量突破/回踩到位/破位信号。")
else:
    for r in res["alerts"]:
        color = st.error if "破位" in r["signal"] else st.success
        color(f"**{r['signal']}**｜{r['code']} {r['name']}（{r['tier']}）"
              f"｜现价 {r['close']}｜量比 {r['volr']}｜RSI {r['rsi']}｜"
              f"入场 {r['entry']}｜止损 {r['stop']}｜目标 {r['target']}｜RR {r['rr']}")

# 分类清单
st.header("📋 分层分类清单")
for cat in dw.CATEGORY_ORDER:
    items = res["by_category"].get(cat, [])
    if not items:
        continue
    st.subheader(f"{cat}（{len(items)}）")
    df = pd.DataFrame([{
        "代码": r["code"], "名称": r["name"], "层": r["tier"], "现价": r["close"],
        "RSI": r["rsi"], "MACD": r["macd"], "MA5": r["ma5"], "MA10": r["ma10"],
        "量比": r["volr"], "换手%": r["turn"], "近20%": r["chg20"], "距52低%": r["dist52"],
        "市值(亿)": (f"{r['cap']}⚠" if r["cap"] and not r["cap_ok"] else r["cap"]),
        "信号": r["signal"], "入场": r["entry"], "止损": r["stop"], "目标": r["target"], "RR": r["rr"],
    } for r in items])
    st.dataframe(df, use_container_width=True, hide_index=True)

st.download_button("⬇️ 导出当日报告(Markdown)", data=dw.build_report_md(res),
                   file_name=f"每日盯盘_{m['time'][:10]}.md", mime="text/markdown")
st.caption("规则：量比>1.3才算放量、站MA5/MA10、破MA5止损、市值20-500亿（超出降级）。"
           "资金面降权。不构成投资建议。")
