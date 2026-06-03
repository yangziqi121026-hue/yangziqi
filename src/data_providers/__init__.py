"""数据源 provider 包。"""

from .base_provider import BaseDataProvider
from .a_share_provider import AShareProvider
from .us_stock_provider import USStockProvider
from .hk_stock_provider import HKStockProvider


def get_provider(market: str) -> BaseDataProvider:
    """根据市场返回对应的数据 provider。

    market 取值: "A股" / "美股" / "港股"
    """
    mapping = {
        "A股": AShareProvider,
        "美股": USStockProvider,
        "港股": HKStockProvider,
    }
    provider_cls = mapping.get(market)
    if provider_cls is None:
        raise ValueError(f"不支持的市场: {market}")
    return provider_cls()


__all__ = [
    "BaseDataProvider",
    "AShareProvider",
    "USStockProvider",
    "HKStockProvider",
    "get_provider",
]
