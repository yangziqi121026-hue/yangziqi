"""交易员。"""

from typing import Dict

from .base_agent import BaseAgent


class Trader(BaseAgent):
    name = "Trader"
    role = "交易员"
    mock_role = "trader"
    system_prompt = (
        "你是 Trader 交易员。"
        "你根据研究经理总结形成交易计划。"
        "你的建议只能是买入、卖出或观望。"
        "必须输出：操作建议、建议仓位、入场区间、止损位置、目标位置、置信度和交易理由。"
        "输出使用简洁的中文 Markdown。"
    )

    def build_user_prompt(self, context: Dict) -> str:
        ind = context.get("indicators", {})
        rm = context.get("agents", {}).get("research_manager", "（无研究经理总结）")
        return (
            f"请根据研究经理的总结形成交易计划：\n\n"
            f"{self.format_stock_info(context)}\n"
            f"支撑位：{ind.get('support')} 压力位：{ind.get('resistance')}\n"
            f"当前趋势：{ind.get('trend')}\n\n"
            f"【研究经理总结】\n{rm}\n\n"
            f"请输出（操作建议只能是 买入/卖出/观望）：操作建议、建议仓位、"
            f"入场区间、止损位置、目标位置、置信度、交易理由。"
        )
