"""港股数据 provider（第一版预留）。

方法签名完整，统一返回 "港股暂未接入" 提示，保证 workflow 不会因
调用缺失方法而崩溃。后续接入真实数据源时只需在此实现。
"""

from typing import Dict

import pandas as pd

from .base_provider import BaseDataProvider

_NOT_READY = "港股暂未接入，将在后续版本中支持。"


class HKStockProvider(BaseDataProvider):
    """港股数据源（占位）。"""

    market_name = "港股"
    currency = "港元 HKD"

    def validate_symbol(self, symbol: str) -> bool:
        return bool(str(symbol).strip())

    def get_stock_name(self, symbol: str) -> str:
        return f"{str(symbol).strip()}（{_NOT_READY}）"

    def get_history(
        self,
        symbol: str,
        start_date: str,
        end_date: str,
        period: str = "daily",
        adjust: str = "qfq",
    ) -> pd.DataFrame:
        return self.empty_history()

    def get_basic_info(self, symbol: str) -> Dict[str, object]:
        return {
            "symbol": str(symbol).strip(),
            "name": None,
            "is_mock": True,
            "note": _NOT_READY,
        }

    def get_financial(self, symbol: str) -> Dict[str, object]:
        return {
            "available": False,
            "summary": _NOT_READY,
            "indicators": {},
        }

    def get_news(self, symbol: str, stock_name: str = "") -> Dict[str, object]:
        return {
            "is_mock": True,
            "items": [_NOT_READY],
            "summary": _NOT_READY,
            "note": _NOT_READY,
        }
