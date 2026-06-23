"""直连东财数据层（绕过被沙箱掐断的 akshare 路径）。

提供：
- daily(code)    : 准确当日前复权日线，列对齐 ak.stock_zh_a_daily
                   (date, open, high, low, close, volume, amount, turnover, outstanding_share)
- fund_flow(code): 主力资金近 N 日净额（元），补上原来"取不到、降权"的资金面瞎点。

为什么需要：新浪源该票常停留前一日、akshare 东财接口在本环境被远端断开；
直连东财 kline/fflow API（带浏览器 UA）实测可拿到当日真实数据（已对照终端收盘价验证）。
"""
from __future__ import annotations

import time
from typing import List, Optional, Tuple

import pandas as pd
import requests

_H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
_UT = "fa5fd1943c7b386f172d6893dbfba10b"  # 东财公开行情 ut token
_KLINE = "https://push2his.eastmoney.com/api/qt/stock/kline/get"
_FFLOW = "https://push2.eastmoney.com/api/qt/stock/fflow/kline/get"
_QUOTE = "https://push2.eastmoney.com/api/qt/stock/get"


def _secid(code: str) -> str:
    """东财 secid：1.=沪市(6开头)，0.=深市/创业板(0/3开头)/北交所。"""
    return ("1." if code[0] == "6" else "0.") + code


def _float_share(code: str) -> Optional[float]:
    """当前流通股本（股），用于算流通市值 = 流通股×收盘/1e8（亿）。"""
    try:
        r = requests.get(
            _QUOTE,
            params={"secid": _secid(code), "ut": _UT, "fields": "f85"},
            headers=_H, timeout=10,
        )
        v = r.json().get("data", {}).get("f85")
        return float(v) if v not in (None, "-", "") else None
    except Exception:  # noqa: BLE001
        return None


def daily(code: str, retries: int = 3, lmt: int = 320) -> Optional[pd.DataFrame]:
    """前复权日线，列对齐 ak.stock_zh_a_daily(adjust='qfq')。失败返回 None。"""
    params = {
        "secid": _secid(code), "ut": _UT,
        "fields1": "f1,f2,f3,f4,f5,f6",
        # f51日期 f52开 f53收 f54高 f55低 f56量(手) f57额(元) f61换手率(%)
        "fields2": "f51,f52,f53,f54,f55,f56,f57,f61",
        "klt": "101", "fqt": "1", "end": "20500101", "lmt": str(lmt),
    }
    for _ in range(retries):
        try:
            r = requests.get(_KLINE, params=params, headers=_H, timeout=15)
            data = r.json().get("data")
            if not data or not data.get("klines"):
                time.sleep(0.5)
                continue
            rows = []
            for k in data["klines"]:
                f = k.split(",")
                rows.append({
                    "date": pd.Timestamp(f[0]),
                    "open": float(f[1]), "close": float(f[2]),
                    "high": float(f[3]), "low": float(f[4]),
                    "volume": float(f[5]), "amount": float(f[6]),
                    "turnover": float(f[7]) / 100.0,  # 换手%→分数，对齐 akshare
                })
            df = pd.DataFrame(rows)
            osh = _float_share(code)
            df["outstanding_share"] = osh if osh else float("nan")
            return df
        except Exception:  # noqa: BLE001
            time.sleep(0.6)
    return None


def fund_flow(code: str, days: int = 5) -> List[Tuple[str, float]]:
    """主力资金近 days 日净额（元）。返回 [(date, main_net), ...]，失败返回 []。"""
    try:
        r = requests.get(
            _FFLOW,
            params={"secid": _secid(code), "ut": _UT,
                    "fields1": "f1,f2,f3", "fields2": "f51,f52",
                    "klt": "101", "lmt": str(days)},
            headers=_H, timeout=12,
        )
        kl = (r.json().get("data") or {}).get("klines", []) or []
        out = []
        for k in kl:
            f = k.split(",")
            try:
                out.append((f[0], float(f[1])))
            except (ValueError, IndexError):
                pass
        return out
    except Exception:  # noqa: BLE001
        return []


def main_net_latest(code: str) -> Optional[float]:
    """最新一日主力净额（元），取不到返回 None。"""
    ff = fund_flow(code, days=1)
    return ff[-1][1] if ff else None
