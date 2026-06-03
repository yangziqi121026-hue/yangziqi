"""观己 ObserveSelf · 产业链 Dashboard 可视化页面。

Streamlit 多页面：放在 pages/ 下会自动出现在侧边栏导航。
只负责渲染，数据/逻辑来自 src/industry_chain.py。

可视化模块：
1. 顶部指标卡（拥挤度/环节数/公司数/整体估值）
2. 产业链流向 Sankey（谁供应谁）
3. 估值-动量四象限散点（谁贵谁涨、资金冷热）
4. 各环节明细（卡脖子/龙头/公司表）
5. 反面推演（观己风险卡）
6. 跟踪指标（验证 vs 证伪）
"""

import os
import sys

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

# 确保可以 import src（兼容多页面运行时的路径）
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from src import industry_chain as ic  # noqa: E402

st.set_page_config(page_title="产业链 Dashboard", page_icon="🧭", layout="wide")

st.title("🧭 观己 ObserveSelf · 产业链 Dashboard")
st.caption("产业链上下游可视化 ｜ 估值-动量扫描 ｜ 反面推演 ｜ 不构成投资建议")

# ----------------------------------------------------------------------------
# 侧边栏：选择产业链关键词
# ----------------------------------------------------------------------------
with st.sidebar:
    st.header("🔍 选择产业链")
    keyword = st.selectbox("投资关键词", ic.list_keywords(), index=0)
    st.markdown("---")
    st.caption("数据为定性判断，需用实时行情核验。")

chain = ic.get_chain(keyword)
if not chain:
    st.error("暂无该关键词的产业链数据。")
    st.stop()

st.warning(
    "⚠️ 本页“估值/涨幅/资金”均为**定性判断 + 区间估计**，非实时数据；"
    "下单前请用项目内 AKShare 管线拉取真实行情核验。本页不构成任何投资建议。"
)

# 一句话逻辑
st.info(
    f"**一句话逻辑：** {chain.get('summary')}\n\n"
    f"**核心驱动：** {chain.get('drivers')}　｜　**核心矛盾：** {chain.get('core_conflict')}"
)

# ----------------------------------------------------------------------------
# 1. 顶部指标卡
# ----------------------------------------------------------------------------
s = ic.stats(chain)
c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("产业链层级", f"{s['tier_count']} 层")
c2.metric("覆盖环节", f"{s['segment_count']} 个")
c3.metric("覆盖公司", f"{s['company_count']} 家")
c4.metric("拥挤度", s["crowding"])
c5.metric("整体估值", s["overall_valuation"])

st.markdown("---")

# ----------------------------------------------------------------------------
# 主体：tabs
# ----------------------------------------------------------------------------
tab_flow, tab_quad, tab_detail, tab_risk, tab_track = st.tabs(
    ["🔗 产业链流向", "🎯 估值-动量四象限", "🏭 各环节明细", "🪞 反面推演", "📡 跟踪指标"]
)

# --- 1. Sankey 产业链流向 ---
with tab_flow:
    st.subheader("谁供应谁（上游 → 中游 → 下游）")
    segments = chain.get("segments", [])
    # 节点：环节名（按出现顺序），标签带层级前缀
    seg_names = [seg["name"] for seg in segments]
    name_to_idx = {n: i for i, n in enumerate(seg_names)}
    tier_color = {"上游": "#ef5350", "中游": "#42a5f5", "下游": "#66bb6a"}
    node_colors = [tier_color.get(seg["tier"], "#90a4ae") for seg in segments]
    node_labels = [f"{seg['tier']}·{seg['name']}" for seg in segments]

    src, tgt, val = [], [], []
    for a, b in chain.get("flow_edges", []):
        if a in name_to_idx and b in name_to_idx:
            src.append(name_to_idx[a])
            tgt.append(name_to_idx[b])
            val.append(1)

    fig_sankey = go.Figure(go.Sankey(
        arrangement="snap",
        node=dict(
            label=node_labels,
            color=node_colors,
            pad=18,
            thickness=18,
            line=dict(color="rgba(0,0,0,0.2)", width=0.5),
        ),
        link=dict(source=src, target=tgt, value=val, color="rgba(120,144,156,0.35)"),
    ))
    fig_sankey.update_layout(height=520, font=dict(size=13))
    st.plotly_chart(fig_sankey, use_container_width=True)
    st.caption("🔴 上游（卡脖子最集中） ｜ 🔵 中游（订单兑现层，A股最能吃肉） ｜ 🟢 下游（需求源头）")

# --- 2. 估值-动量四象限 ---
with tab_quad:
    st.subheader("估值 × 动量 四象限（气泡颜色=资金属性）")
    rows = [r for r in ic.all_companies(chain) if r["name"] != "(需求源头)"]
    fig_q = go.Figure()
    for r in rows:
        fig_q.add_trace(go.Scatter(
            x=[r["valuation_score"]], y=[r["change_score"]],
            mode="markers+text",
            marker=dict(size=26, color=r["color"], line=dict(color="white", width=1)),
            text=[r["name"]], textposition="top center",
            name=r["name"],
            hovertemplate=(
                f"<b>{r['name']}</b>（{r['segment']}）<br>"
                f"角色：{r['role']}<br>估值：{r['valuation']}<br>"
                f"涨幅：{r['change']}<br>资金：{r['fund']}<br>{r['note']}<extra></extra>"
            ),
        ))
    # 象限分割线
    fig_q.add_hline(y=3, line_dash="dot", line_color="gray")
    fig_q.add_vline(x=3, line_dash="dot", line_color="gray")
    fig_q.add_annotation(x=4.5, y=4.7, text="高估值·高动量<br>（拥挤/透支风险）", showarrow=False, font=dict(color="#e53935"))
    fig_q.add_annotation(x=1.6, y=4.7, text="低估值·高动量<br>（价值+动量）", showarrow=False, font=dict(color="#43a047"))
    fig_q.add_annotation(x=1.6, y=1.3, text="低估值·低动量<br>（冷门/潜伏）", showarrow=False, font=dict(color="#1e88e5"))
    fig_q.add_annotation(x=4.5, y=1.3, text="高估值·低动量<br>（最危险）", showarrow=False, font=dict(color="#8e24aa"))
    fig_q.update_layout(
        height=560, showlegend=False,
        xaxis=dict(title="估值（越右越贵·定性评分）", range=[0.5, 5.5]),
        yaxis=dict(title="近期动量（越上涨得越多·定性评分）", range=[0.5, 5.5]),
    )
    st.plotly_chart(fig_q, use_container_width=True)
    st.caption("评分为定性映射，仅用于相对比较；右上象限拥挤度最高，回撤风险也最大。")

# --- 3. 各环节明细 ---
with tab_detail:
    st.subheader("各环节：卡脖子 / 龙头 / 代表公司")
    for seg in chain.get("segments", []):
        tier_badge = {"上游": "🔴 上游", "中游": "🔵 中游", "下游": "🟢 下游"}.get(seg["tier"], seg["tier"])
        with st.expander(f"{tier_badge}｜{seg['name']}　（龙头：{seg['leader']}）", expanded=False):
            st.markdown(f"**卡脖子点：** {seg['bottleneck']}")
            df = pd.DataFrame(seg["companies"])
            if not df.empty:
                df = df.rename(columns={
                    "name": "公司", "role": "卡位", "valuation": "估值",
                    "change": "涨幅", "fund": "资金", "note": "观己提示",
                })
                st.dataframe(df, use_container_width=True, hide_index=True)

# --- 4. 反面推演 ---
with tab_risk:
    st.subheader("🪞 观己模块 · 万一呢？")
    st.caption("不找上涨理由，专门攻击自己的逻辑。")
    risks = chain.get("risks", [])
    cols = st.columns(2)
    for i, rk in enumerate(risks):
        with cols[i % 2]:
            st.error(f"**{rk['title']}**\n\n{rk['detail']}")
    st.markdown("---")
    st.markdown("**卡脖子地图：**")
    for b in chain.get("bottlenecks", []):
        st.markdown(f"- {b}")

# --- 5. 跟踪指标 ---
with tab_track:
    st.subheader("📡 验证 vs 证伪 信号")
    ind = chain.get("indicators", [])
    if ind:
        df = pd.DataFrame(ind).rename(columns={
            "category": "类别", "bull": "✅ 看多验证", "bear": "❌ 看空证伪",
        })
        st.dataframe(df, use_container_width=True, hide_index=True)
    st.markdown(
        "> **灵魂自检：** 我现在想买，是因为「逻辑变好了」，还是「它涨了我怕踏空」？"
        "—— 后者是危险信号。"
    )

st.markdown("---")
st.caption("本报告由 AI 推理引擎生成，仅供研究学习，不构成任何投资建议；数据以实时行情核验为准。")
