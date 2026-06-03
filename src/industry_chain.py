"""产业链结构化数据 + 观己 ObserveSelf 产业链分析数据层。

把产业链知识沉淀为结构化数据，供 Dashboard 可视化页面消费。
业务/数据放这里，页面只负责渲染（与 app.py 同样的分层原则）。

注意：估值/涨幅/资金均为“定性判断”，需用实时数据核验，不构成投资建议。
"""

from typing import Dict, List

# ----------------------------------------------------------------------------
# 定性 -> 评分映射（仅用于可视化排序/象限，非真实市场数据）
# ----------------------------------------------------------------------------
VALUATION_SCORE = {"便宜": 1, "中性": 2, "中性偏贵": 2.5, "偏贵": 3, "很贵": 4, "极贵": 5}
CHANGE_SCORE = {"滞涨": 1, "温和": 1.5, "上涨": 2, "显著上涨": 3, "大幅上涨": 4, "大幅领涨": 4.5, "暴涨暴跌": 5, "高波动大涨": 4.5}
FUND_COLOR = {
    "流出": "#9e9e9e",
    "一般": "#90a4ae",
    "关注升": "#42a5f5",
    "主力关注": "#1e88e5",
    "北上+机构": "#1565c0",
    "活跃": "#fb8c00",
    "题材资金": "#e53935",
    "强题材": "#b71c1c",
}


def valuation_to_score(v: str) -> float:
    return VALUATION_SCORE.get(v, 2.5)


def change_to_score(c: str) -> float:
    return CHANGE_SCORE.get(c, 2.0)


def fund_to_color(f: str) -> str:
    return FUND_COLOR.get(f, "#90a4ae")


# ----------------------------------------------------------------------------
# 产业链数据
# ----------------------------------------------------------------------------
_AI_DC = {
    "keyword": "AI 数据中心",
    "summary": "把模型训练/推理的算力需求，翻译成从芯片到机柜的一长串硬件采购订单。",
    "drivers": "北美 CSP + 国内云厂资本开支（CapEx）增速。",
    "core_conflict": "高端算力被卡脖子（出口管制/先进制程） vs 国产替代。",
    "crowding": "高",
    "overall_valuation": "偏高",
    # 各环节（含代表公司的定性扫描）
    "segments": [
        {
            "tier": "上游", "name": "AI芯片/GPU",
            "bottleneck": "美国出口管制 + 先进制程", "leader": "英伟达 / 海光·寒武纪(国产)",
            "companies": [
                {"name": "海光信息", "role": "国产CPU/DCU", "valuation": "很贵", "change": "高波动大涨", "fund": "题材资金", "note": "估值靠国产替代叙事"},
                {"name": "寒武纪", "role": "国产AI芯片", "valuation": "极贵", "change": "暴涨暴跌", "fund": "强题材", "note": "典型故事股，证伪风险大"},
            ],
        },
        {
            "tier": "上游", "name": "存储HBM",
            "bottleneck": "高带宽存储产能紧", "leader": "SK海力士",
            "companies": [
                {"name": "SK海力士", "role": "HBM龙头(海外)", "valuation": "中性偏贵", "change": "显著上涨", "fund": "北上+机构", "note": "A股可关注存储模组/封测配套"},
            ],
        },
        {
            "tier": "上游", "name": "光模块/光芯片",
            "bottleneck": "800G/1.6T升级节奏；光芯片国产化率低", "leader": "中际旭创",
            "companies": [
                {"name": "中际旭创", "role": "光模块龙头", "valuation": "偏贵", "change": "大幅领涨", "fund": "主力关注", "note": "众所周知的好，预期已高"},
                {"name": "新易盛", "role": "光模块", "valuation": "偏贵", "change": "大幅上涨", "fund": "活跃", "note": "弹性大=波动大"},
                {"name": "天孚通信", "role": "光器件", "valuation": "偏贵", "change": "显著上涨", "fund": "活跃", "note": "光模块上游配套"},
            ],
        },
        {
            "tier": "上游", "name": "PCB/覆铜板",
            "bottleneck": "高多层/高频高速材料", "leader": "沪电股份",
            "companies": [
                {"name": "沪电股份", "role": "高速PCB", "valuation": "偏贵", "change": "显著上涨", "fund": "活跃", "note": "受PCB升级周期驱动"},
                {"name": "生益科技", "role": "覆铜板", "valuation": "中性偏贵", "change": "上涨", "fund": "关注升", "note": "材料端，弹性相对温和"},
            ],
        },
        {
            "tier": "中游", "name": "服务器/ODM",
            "bottleneck": "高端GPU供给（受制上游）", "leader": "工业富联",
            "companies": [
                {"name": "工业富联", "role": "服务器ODM龙头", "valuation": "中性偏贵", "change": "显著上涨", "fund": "北上+机构", "note": "体量大、确定性高、弹性低"},
                {"name": "浪潮信息", "role": "服务器", "valuation": "中性偏贵", "change": "显著上涨", "fund": "活跃", "note": "国产算力服务器主力"},
            ],
        },
        {
            "tier": "中游", "name": "交换机/网络",
            "bottleneck": "高速组网芯片", "leader": "紫光股份 / 锐捷网络",
            "companies": [
                {"name": "紫光股份", "role": "新华三(交换机)", "valuation": "中性", "change": "上涨", "fund": "关注升", "note": "网络设备龙头"},
                {"name": "锐捷网络", "role": "交换机", "valuation": "中性偏贵", "change": "上涨", "fund": "活跃", "note": "数据中心交换机弹性标的"},
            ],
        },
        {
            "tier": "中游", "name": "液冷/温控",
            "bottleneck": "高功率密度散热", "leader": "英维克",
            "companies": [
                {"name": "英维克", "role": "液冷温控龙头", "valuation": "中性偏贵", "change": "上涨", "fund": "关注升", "note": "液冷渗透率是关键变量"},
                {"name": "申菱环境", "role": "数据中心温控", "valuation": "中性", "change": "上涨", "fund": "关注升", "note": "工艺空调切入液冷"},
            ],
        },
        {
            "tier": "中游", "name": "电源/供配电",
            "bottleneck": "高效率电源", "leader": "麦格米特",
            "companies": [
                {"name": "麦格米特", "role": "电源", "valuation": "中性偏贵", "change": "上涨", "fund": "活跃", "note": "切入AI服务器电源"},
                {"name": "科华数据", "role": "数据中心供配电/IDC", "valuation": "中性", "change": "温和", "fund": "一般", "note": "兼具IDC运营"},
            ],
        },
        {
            "tier": "下游", "name": "IDC运营/建设",
            "bottleneck": "电力指标/上架率", "leader": "润泽科技",
            "companies": [
                {"name": "润泽科技", "role": "IDC运营", "valuation": "中性", "change": "温和", "fund": "一般", "note": "重资产，看上架率与电价"},
                {"name": "光环新网", "role": "IDC运营", "valuation": "中性", "change": "温和", "fund": "一般", "note": "一线城市机柜资源"},
            ],
        },
        {
            "tier": "下游", "name": "云厂/互联网(需求端)",
            "bottleneck": "AI应用变现能力", "leader": "阿里 / 腾讯 / 字节 / 北美CSP",
            "companies": [
                {"name": "(需求源头)", "role": "下订单的人", "valuation": "中性", "change": "温和", "fund": "一般", "note": "CapEx指引是全链先行指标"},
            ],
        },
    ],
    # 供应流向（source 环节 -> target 环节），用于 Sankey
    "flow_edges": [
        ("AI芯片/GPU", "服务器/ODM"),
        ("存储HBM", "服务器/ODM"),
        ("光模块/光芯片", "交换机/网络"),
        ("光模块/光芯片", "服务器/ODM"),
        ("PCB/覆铜板", "服务器/ODM"),
        ("PCB/覆铜板", "交换机/网络"),
        ("电源/供配电", "服务器/ODM"),
        ("液冷/温控", "服务器/ODM"),
        ("服务器/ODM", "IDC运营/建设"),
        ("交换机/网络", "IDC运营/建设"),
        ("IDC运营/建设", "云厂/互联网(需求端)"),
    ],
    "bottlenecks": [
        "高端 GPU：美国出口管制，国产替代是长期主线但短期供给受限。",
        "HBM：高带宽存储产能紧张，受海外大厂主导。",
        "先进制程/光刻：最底层的卡脖子，决定算力上限。",
    ],
    "risks": [
        {"title": "万一逻辑错了（需求证伪）", "detail": "云厂CapEx顺周期，指引一旦下修，最贵的光模块/国产芯片杀得最快；AI应用不赚钱→质疑算力回报比→杀逻辑。"},
        {"title": "万一已经涨完了（拥挤透支）", "detail": "机构高度抱团、人人皆知的主线，好逻辑≠好买点；警惕利好兑现即出货。"},
        {"title": "万一技术路线被颠覆", "detail": "CPO加速可能重构光模块格局；更省算力的模型架构会削弱无限堆算力的叙事。"},
        {"title": "万一政策/外部冲击", "detail": "出口管制加码或放松，都会让国产算力链剧烈波动。"},
        {"title": "估值反噬", "detail": "增速从100%降到40%（仍高）也会戴维斯双杀，增速的加速度比绝对值更重要。"},
    ],
    "indicators": [
        {"category": "需求", "bull": "北美CSP上调CapEx指引", "bear": "CSP下修 / 国内云厂砍单"},
        {"category": "订单", "bull": "光模块/服务器排产超预期", "bear": "订单环比走弱、库存上升"},
        {"category": "价格", "bull": "800G→1.6T升级提速、涨价", "bear": "价格战、毛利下滑"},
        {"category": "渗透", "bull": "液冷渗透率快速提升", "bear": "液冷推进慢于预期"},
        {"category": "资金", "bull": "龙头放量上行、北上加仓", "bear": "高位放量滞涨、龙头补跌"},
    ],
}

CHAINS: Dict[str, dict] = {
    "AI 数据中心": _AI_DC,
}


def list_keywords() -> List[str]:
    """返回已内置的产业链关键词。"""
    return list(CHAINS.keys())


def get_chain(keyword: str) -> dict:
    """获取指定关键词的产业链数据，找不到返回空结构。"""
    return CHAINS.get(keyword, {})


def all_companies(chain: dict) -> List[dict]:
    """展平所有环节的公司，并附带所属环节与层级，便于做散点/表格。"""
    rows = []
    for seg in chain.get("segments", []):
        for c in seg.get("companies", []):
            rows.append({
                "tier": seg["tier"],
                "segment": seg["name"],
                "name": c["name"],
                "role": c["role"],
                "valuation": c["valuation"],
                "change": c["change"],
                "fund": c["fund"],
                "note": c["note"],
                "valuation_score": valuation_to_score(c["valuation"]),
                "change_score": change_to_score(c["change"]),
                "color": fund_to_color(c["fund"]),
            })
    return rows


def stats(chain: dict) -> dict:
    """汇总用于顶部指标卡的统计。"""
    segs = chain.get("segments", [])
    comps = all_companies(chain)
    return {
        "segment_count": len(segs),
        "company_count": len([c for c in comps if c["name"] != "(需求源头)"]),
        "tier_count": len({s["tier"] for s in segs}),
        "crowding": chain.get("crowding", "未知"),
        "overall_valuation": chain.get("overall_valuation", "未知"),
    }
