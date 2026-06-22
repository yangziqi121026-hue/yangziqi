"""DeepSeek 精析层：对短线选股引擎筛出的候选做精细化二次研判。

定位：选股引擎(screener.py)负责“用硬规则筛出有数据支撑的候选”，
本模块负责“让 LLM(默认 DeepSeek)站在超短线交易员角度，对每只候选的
RSI/超卖反弹逻辑做确认或否决、点评价位、补充反面风险、给置信度”。

- 复用统一的 llm_client（已支持 DeepSeek/OpenAI 兼容 + Mock 降级）。
- 无 Key / MOCK_MODE=true 时返回清晰的占位分析，不会崩。
- 不构成投资建议。
"""

from typing import Dict, List

from .llm_client import llm_client

SYSTEM_PROMPT = (
    "你是资深A股超短线交易员，专注1–5天、只做有数据有逻辑有风控的标的，"
    "尤其擅长 RSI 超卖/中性区的低吸反弹与放量突破。"
    "你会基于给定的量化指标，冷静判断该标的的超卖反弹逻辑是否成立，"
    "并从反面提示风险。你不打板、不追高、不说空话，"
    "只输出可执行结论。绝不编造未给出的数据。不构成投资建议。"
)


def _build_prompt(c: Dict, market_env: Dict) -> str:
    """把单只候选的量化数据组织成给 LLM 的精析提示。"""
    price = c.get("price")

    def _pos(ma):
        if price is None or ma is None:
            return "?"
        return "站上" if price >= ma else "跌破"

    ma_pos = f"现价{_pos(c.get('ma5'))}MA5、{_pos(c.get('ma10'))}MA10、{_pos(c.get('ma20'))}MA20"
    return (
        f"【大盘环境】趋势：{market_env.get('trend')}；量能：{market_env.get('volume')}；"
        f"情绪：{market_env.get('sentiment')}；建议总仓位：{market_env.get('suggested_position')}\n\n"
        f"【候选标的】{c.get('code')} {c.get('name')}　现价 {c.get('price')}\n"
        f"- RSI14：{c.get('rsi')}（{'超卖' if (c.get('rsi') or 50) < 30 else '中性区'}）\n"
        f"- MACD：{c.get('macd_state')}\n"
        f"- 均线：MA5={c.get('ma5')} MA10={c.get('ma10')} MA20={c.get('ma20')} MA60={c.get('ma60')}（{ma_pos}）\n"
        f"- 距52周低：{c.get('dist_52w_low_pct')}%　近20日涨幅：{c.get('chg20')}%\n"
        f"- 量比：{c.get('vol_ratio')}　换手：{c.get('turnover')}%　流通市值：{c.get('float_cap_yi')}亿\n"
        f"- 题材：{c.get('theme')}　基本面：{c.get('fund_status')}\n"
        f"- 引擎给的价位：入场 {c.get('entry_low')}~{c.get('entry_high')}，"
        f"止损 {c.get('stop')}，目标 {c.get('target')}，盈亏比 {c.get('rr')}\n\n"
        f"请用不超过 6 行，输出：\n"
        f"1) 超卖/反弹逻辑是否成立（成立/存疑/否决，一句话理由）\n"
        f"2) RSI+MACD 角度的点评\n"
        f"3) 最大反面风险（万一逻辑错了）\n"
        f"4) 入场/止损/目标是否合理，需否微调\n"
        f"5) 短线置信度（高/中/低）\n"
    )


def analyze_one(candidate: Dict, market_env: Dict) -> str:
    """对单只候选做 DeepSeek 精析，返回 Markdown 文本。"""
    return llm_client.chat(
        system_prompt=SYSTEM_PROMPT,
        user_prompt=_build_prompt(candidate, market_env),
        temperature=0.3,
        max_tokens=600,
        mock_role="deepseek_short",
    )


def assess_confidence(candidate: Dict, market_env: Dict) -> str:
    """只评短线置信度，返回 高/中/低。用 temperature=0 求确定性，修单次调用 中↔低 跳变。
    门槛专用：若解析失败按"中"处理(不误杀)。"""
    import re
    prompt = (
        _build_prompt(candidate, market_env)
        + "\n\n请只回一行：『置信度：高』或『置信度：中』或『置信度：低』，不要其它内容。"
    )
    try:
        txt = llm_client.chat(system_prompt=SYSTEM_PROMPT, user_prompt=prompt,
                              temperature=0.0, max_tokens=20, mock_role="deepseek_short")
    except Exception:  # noqa: BLE001
        return "中"
    m = re.search(r"(高|中|低)", txt)
    return m.group(1) if m else "中"


def analyze_candidates(candidates: List[Dict], market_env: Dict) -> Dict[str, str]:
    """批量精析，返回 {code: 分析文本}。任何单只出错不影响其余。"""
    out: Dict[str, str] = {}
    for c in candidates:
        code = c.get("code", "?")
        try:
            out[code] = analyze_one(c, market_env)
        except Exception as exc:  # noqa: BLE001
            out[code] = f"> ⚠️ 该标的精析失败：{exc}（不影响其余标的）"
    return out


def is_real_llm() -> bool:
    """当前是否使用真实 LLM（非 mock）。供界面提示。"""
    return not getattr(llm_client, "mock_mode", True)


def test_connection() -> dict:
    """测试 DeepSeek/LLM API 连接，返回 {ok, provider, model, message}。"""
    return llm_client.test_connection()
