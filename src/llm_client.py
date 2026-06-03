"""LLM 客户端封装。

- 支持 OpenAI 兼容接口（通过 OPENAI_BASE_URL 可指向任意兼容服务）。
- 支持 mock 模式：没有 API Key 或 MOCK_MODE=true 时自动使用内置占位输出。
- 不会因为缺少 Key 而崩溃，保证整个系统可在无网络/无 Key 情况下跑通。
"""

from typing import Optional

from .config import config


class LLMClient:
    """统一的 LLM 调用入口。"""

    def __init__(self) -> None:
        self.mock_mode = config.is_mock_mode()
        self.model = config.MODEL_NAME
        self._client = None

        if not self.mock_mode:
            # 仅在真实模式下尝试初始化 OpenAI 客户端
            try:
                from openai import OpenAI

                self._client = OpenAI(
                    api_key=config.OPENAI_API_KEY,
                    base_url=config.OPENAI_BASE_URL,
                )
            except Exception as exc:  # noqa: BLE001
                # 初始化失败则自动降级到 mock，保证系统不中断
                print(f"[LLMClient] 初始化真实客户端失败，自动降级 mock 模式: {exc}")
                self.mock_mode = True
                self._client = None

    def chat(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.4,
        max_tokens: int = 1200,
        mock_role: Optional[str] = None,
    ) -> str:
        """调用 LLM 并返回纯文本结果。

        mock_role 用于在 mock 模式下选择对应角色的占位输出。
        """
        if self.mock_mode or self._client is None:
            return _mock_response(mock_role, user_prompt)

        try:
            resp = self._client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=temperature,
                max_tokens=max_tokens,
            )
            content = resp.choices[0].message.content
            return content.strip() if content else _mock_response(mock_role, user_prompt)
        except Exception as exc:  # noqa: BLE001
            # 任何调用异常都降级到 mock，并在结果中提示
            return (
                f"> ⚠️ LLM 调用失败，已使用占位输出。错误信息：{exc}\n\n"
                + _mock_response(mock_role, user_prompt)
            )


# ----------------------------------------------------------------------------
# Mock 输出：保证无 Key / 无网络也能跑通完整流程
# ----------------------------------------------------------------------------

_MOCK_TEMPLATES = {
    "fundamental": (
        "**基本面判断（占位输出）**\n\n"
        "- 营收与利润：根据已获取数据，公司营收呈现一定波动，需结合最新财报确认。\n"
        "- 估值水平：当前估值处于行业中性区间（占位）。\n"
        "- 成长性：成长性中等，需观察后续季度增速。\n"
        "- 财务健康度：现金流与负债结构总体可控（占位）。\n"
        "- ⚠️ 若财务数据不足，本结论可信度下降。\n\n"
        "（注：当前为 Mock 模式输出，仅用于流程演示，不构成投资建议。）"
    ),
    "news": (
        "**新闻面利好与利空（占位输出）**\n\n"
        "- 潜在利好：行业政策总体偏暖，公司近期无重大负面公告（占位）。\n"
        "- 潜在利空：宏观需求存在不确定性，需关注外部环境（占位）。\n"
        "- 新闻面结论：新闻面整体中性偏暖。\n\n"
        "> ⚠️ 新闻数据为模拟/占位，需接入真实新闻源后提高可信度。\n"
        "（注：当前为 Mock 模式输出。）"
    ),
    "sentiment": (
        "**市场情绪判断（占位输出）**\n\n"
        "- 市场情绪：中性偏多。\n"
        "- 量价情绪：成交量变化温和，未见明显恐慌或亢奋（占位）。\n"
        "- 投资者偏好：关注度一般。\n"
        "- 情绪面结论：情绪面中性，缺乏极端信号。\n\n"
        "（注：当前为 Mock 模式输出。）"
    ),
    "technical": (
        "**技术面结论（占位输出）**\n\n"
        "- 趋势：根据均线排列判断为震荡偏多（占位）。\n"
        "- 均线：短期均线与中期均线纠缠，方向待明确。\n"
        "- RSI：处于中性区间，无超买超卖。\n"
        "- MACD：动能中性。\n"
        "- 支撑/压力：参考近 60 日高低点。\n"
        "- 技术面结论：技术面中性，等待方向选择。\n\n"
        "（注：当前为 Mock 模式输出。）"
    ),
    "bull": (
        "**看涨理由（占位输出）**\n\n"
        "1. 行业景气度有望回升，公司具备一定竞争壁垒。\n"
        "2. 估值并不昂贵，存在修复空间。\n"
        "3. 技术面若站稳均线，可能开启上行。\n"
        "4. 市场情绪未过热，仍有增量资金空间。\n\n"
        "（注：当前为 Mock 模式输出，仅站在看涨立场。）"
    ),
    "bear": (
        "**看跌风险（占位输出）**\n\n"
        "1. 宏观需求与外部环境存在不确定性。\n"
        "2. 财务/新闻数据若不足，基本面存在盲区。\n"
        "3. 技术面尚未明确转强，存在回调风险。\n"
        "4. 成交量若萎缩，上行动能不足。\n\n"
        "（注：当前为 Mock 模式输出，仅站在看跌立场。）"
    ),
    "research_manager": (
        "**研究经理总结（占位输出）**\n\n"
        "- 多空力量对比：多空力量大致均衡，多头略占小幅优势（占位）。\n"
        "- 核心矛盾：基本面/新闻数据完整度与技术面方向尚未明确。\n"
        "- 研究结论：建议以观望为主，等待更明确信号后再决策。\n\n"
        "（注：当前为 Mock 模式输出，不直接下单。）"
    ),
    "trader": (
        "**交易计划（占位输出）**\n\n"
        "- 操作建议：观望\n"
        "- 建议仓位：0%~10%（轻仓试探）\n"
        "- 入场区间：参考支撑位附近分批\n"
        "- 止损位置：跌破近期支撑位\n"
        "- 目标位置：近期压力位\n"
        "- 置信度：中（占位）\n"
        "- 交易理由：信号不明确，控制风险优先。\n\n"
        "（注：当前为 Mock 模式输出，不构成投资建议。）"
    ),
    "risk_manager": (
        "**风控结论（占位输出）**\n\n"
        "- 风险等级：中\n"
        "- 是否允许交易：谨慎\n"
        "- 最大风险点：数据完整度不足 + 趋势不明确。\n"
        "- 仓位控制：建议总仓位不超过 10%~20%，严格止损。\n"
        "- 风控备注：当前为 Mock 模式，结论仅供流程演示，务必结合真实数据复核。\n\n"
        "（注：当前为 Mock 模式输出。）"
    ),
}


def _mock_response(role: Optional[str], user_prompt: str) -> str:
    """根据角色返回占位文本。"""
    if role and role in _MOCK_TEMPLATES:
        return _MOCK_TEMPLATES[role]
    return (
        "**（占位输出）**\n\n"
        "当前处于 Mock 模式，未调用真实大模型。\n"
        "以下为基于输入数据的占位分析，仅用于演示完整流程，不构成投资建议。"
    )


# 全局单例，方便智能体直接使用
llm_client = LLMClient()
