"""query_attractions — Generate attractions from LLM knowledge."""

from __future__ import annotations

from travel_agent.llm import generate_with_examples

_ATTRACTION_EXAMPLES = [
    {
        "destination": "云南",
        "interests": "亲子",
        "attractions": [
            {"name": "滇池", "description": "高原湖泊，可喂海鸥", "duration": "半天"},
            {"name": "石林", "description": "喀斯特地貌奇观", "duration": "一天"},
            {"name": "丽江古城", "description": "世界文化遗产", "duration": "一天"},
            {"name": "大理古城", "description": "白族文化古城", "duration": "半天"},
            {"name": "玉龙雪山", "description": "海拔5596米雪山", "duration": "一天"},
            {"name": "西双版纳热带植物园", "description": "丰富的热带植物", "duration": "一天"},
        ],
    },
    {
        "destination": "北京",
        "interests": "历史文化",
        "attractions": [
            {"name": "故宫博物院", "description": "明清皇家宫殿", "duration": "半天到一天"},
            {"name": "长城", "description": "世界奇迹", "duration": "一天"},
            {"name": "天坛", "description": "明清皇帝祭天场所", "duration": "半天"},
            {"name": "颐和园", "description": "皇家园林", "duration": "半天"},
        ],
    },
]

_ATTRACTION_SYSTEM_PROMPT = """你是旅行景点知识助手。根据目的地和兴趣推荐景点。

请以 JSON 数组格式返回景点列表，每个景点包含：
- name: 景点名称
- description: 简短描述（10-30字）
- duration: 建议游玩时间
- tips: 游玩小贴士（可选）

只输出 JSON 数组，不要其他文字。"""


def query_attractions(destination: str, interests: str = "") -> str:
    """查询目的地景点推荐。

    Args:
        destination: 目的地，如"云南"、"大理"。
        interests: 兴趣偏好，如"亲子"、"自然风光"、"历史文化"。

    Returns:
        景点推荐列表文本。
    """
    user_msg = f"目的地：{destination}，兴趣偏好：{interests or '不限'}"
    raw = generate_with_examples(_ATTRACTION_SYSTEM_PROMPT, user_msg, _ATTRACTION_EXAMPLES)

    import json
    import re

    # Try to extract and format JSON result
    json_match = re.search(r'\[.*\]', raw, re.DOTALL)
    if not json_match:
        return f"无法获取 {destination} 的景点信息"

    try:
        attractions = json.loads(json_match.group())
        if not attractions:
            return f"未找到 {destination} 的景点信息"

        lines = [f"推荐 {destination} 景点："]
        for i, a in enumerate(attractions, 1):
            name = a.get("name", "")
            desc = a.get("description", "")
            duration = a.get("duration", "")
            tips = a.get("tips", "")
            line = f"  {i}. {name}"
            if desc:
                line += f" — {desc}"
            if duration:
                line += f"（建议{duration}）"
            if tips:
                line += f"\n     tip：{tips}"
            lines.append(line)
        return "\n".join(lines)
    except json.JSONDecodeError:
        return f"无法获取 {destination} 的景点信息"
