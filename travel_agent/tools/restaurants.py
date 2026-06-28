"""query_restaurants — Generate restaurants from LLM knowledge."""

from __future__ import annotations

from travel_agent.llm import generate_with_examples

_RESTAURANT_EXAMPLES = [
    {
        "location": "云南",
        "taste": "亲子",
        "restaurants": [
            {"name": "过桥米线", "cuisine": "云南特色", "price_range": "30-80元/人"},
            {"name": "汽锅鸡", "cuisine": "云南菜", "price_range": "50-120元/人"},
            {"name": "野生菌火锅", "cuisine": "云南特色", "price_range": "80-200元/人"},
            {"name": "烤乳扇", "cuisine": "大理小吃", "price_range": "10-20元/份"},
        ],
    },
    {
        "location": "成都",
        "taste": "爱吃辣",
        "restaurants": [
            {"name": "火锅", "cuisine": "川味火锅", "price_range": "80-150元/人"},
            {"name": "夫妻肺片", "cuisine": "川菜凉菜", "price_range": "30-60元/人"},
            {"name": "担担面", "cuisine": "成都小吃", "price_range": "10-20元/碗"},
        ],
    },
]

_RESTAURANT_SYSTEM_PROMPT = """你是旅行美食推荐助手。根据目的地和口味偏好推荐餐厅。

请以 JSON 数组格式返回餐厅列表，每个餐厅包含：
- name: 餐厅/菜品名
- cuisine: 菜系类型
- price_range: 人均价格范围
- recommendation: 推荐理由（可选）

只输出 JSON 数组，不要其他文字。"""


def query_restaurants(location: str, taste: str = "") -> str:
    """查询目的地餐厅推荐。

    Args:
        location: 地点，如"云南"、"大理古城"。
        taste: 口味偏好，如"爱吃辣"、"清淡"、"本地特色"。

    Returns:
        餐厅推荐列表文本。
    """
    user_msg = f"地点：{location}，口味偏好：{taste or '不限'}"
    raw = generate_with_examples(_RESTAURANT_SYSTEM_PROMPT, user_msg, _RESTAURANT_EXAMPLES)

    import json
    import re

    json_match = re.search(r'\[.*\]', raw, re.DOTALL)
    if not json_match:
        return f"无法获取 {location} 的餐厅信息"

    try:
        restaurants = json.loads(json_match.group())
        if not restaurants:
            return f"未找到 {location} 的餐厅信息"

        lines = [f"推荐 {location} 美食/餐厅："]
        for i, r in enumerate(restaurants, 1):
            name = r.get("name", "")
            cuisine = r.get("cuisine", "")
            price = r.get("price_range", "")
            recommend = r.get("recommendation", "")
            line = f"  {i}. {name}"
            if cuisine:
                line += f"（{cuisine}）"
            line += f"，人均{price}"
            if recommend:
                line += f"\n     推荐理由：{recommend}"
            lines.append(line)
        return "\n".join(lines)
    except json.JSONDecodeError:
        return f"无法获取 {location} 的餐厅信息"
