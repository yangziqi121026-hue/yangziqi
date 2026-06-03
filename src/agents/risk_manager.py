"""风控员。"""

from typing import Dict

from .base_agent import BaseAgent


class RiskManager(BaseAgent):
    name = "Risk Manager"
    role = "风控员"
    mock_role = "risk_manager"
    system_prompt = (
        "你是 Risk Manager 风控员。"
        "你负责审核交易员建议，判断风险等级和是否允许执行。"
        "你必须保守，不要盲目支持交易。"
        "必须输出：风险等级、是否允许交易、最大风险点、仓位控制和风控备注。"
        "输出使用简洁的中文 Markdown。"
    )

    def build_user_prompt(self, context: Dict) -> str:
        trader = context.get("agents", {}).get("trader", "（无交易员建议）")
        dq = context.get("data_quality", {})
        return (
            f"请审核以下交易员建议并给出风控结论：\n\n"
            f"{self.format_stock_info(context)}\n\n"
            f"【交易员建议】\n{trader}\n\n"
            f"【数据质量提示】\n"
            f"行情数据：{dq.get('price')}\n"
            f"财务数据：{dq.get('financial')}\n"
            f"新闻数据：{dq.get('news')}\n\n"
            f"请保守地输出（风险等级 低/中/高；是否允许交易 允许/谨慎/不建议）："
            f"风险等级、是否允许交易、最大风险点、仓位控制建议、风控备注。"
        )
