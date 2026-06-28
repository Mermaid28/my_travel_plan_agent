"""LLM API call wrapper using OpenAI SDK."""

from __future__ import annotations

import json
import os
from typing import Optional

from openai import OpenAI

from travel_agent.session import Message, ToolCall


def _sanitize(text: str) -> str:
    """Remove surrogate characters and other problematic Unicode."""
    return text.encode("utf-8", errors="replace").decode("utf-8")


def _get_env_or_raise(key: str) -> str:
    val = os.environ.get(key)
    if not val:
        raise ValueError(f"Missing required environment variable: {key}")
    return val


_client: Optional[OpenAI] = None
_model: Optional[str] = None


def get_client() -> OpenAI:
    """Get or initialize the OpenAI client from environment variables."""
    global _client
    if _client is None:
        api_key = _get_env_or_raise("LLM_API_KEY")
        base_url = os.environ.get("LLM_BASE_URL", "https://api.deepseek.com")
        _client = OpenAI(api_key=api_key, base_url=base_url)
    return _client


def get_model() -> str:
    """Get the model name from environment variable."""
    global _model
    if _model is None:
        _model = os.environ.get("LLM_MODEL", "deepseek-chat")
    return _model


def call_llm(
    messages: list[Message],
    tools: Optional[list[dict]] = None,
    temperature: float = 0.7,
) -> Message:
    """Call the LLM and return the response as a Message.

    Args:
        messages: List of Messages (converted to OpenAI format internally).
        tools: OpenAI-format tool definitions (from ToolRegistry.get_openai_tools()).
        temperature: Sampling temperature.

    Returns:
        An assistant Message — either with .content text or .tool_calls.
    """
    client = get_client()
    model = get_model()
    openai_messages = [m.to_openai() for m in messages]

    kwargs = dict(model=model, messages=openai_messages, temperature=temperature)
    if tools:
        kwargs["tools"] = tools

    response = client.chat.completions.create(**kwargs)
    choice = response.choices[0]
    msg = choice.message

    content = _sanitize(msg.content or "")

    tool_calls = None
    if msg.tool_calls:
        tool_calls = []
        for tc in msg.tool_calls:
            args = tc.function.arguments
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except json.JSONDecodeError:
                    pass
            tool_calls.append(ToolCall(id=tc.id, name=tc.function.name, arguments=args))

    return Message(role="assistant", content=content, tool_calls=tool_calls)


def call_llm_simple(
    system_prompt: str,
    user_message: str,
    temperature: float = 0.5,
) -> str:
    """Simplified LLM call for internal use (no tools).

    Used by query_attractions / query_restaurants tools.
    """
    client = get_client()
    model = get_model()
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
        temperature=temperature,
    )
    return _sanitize(response.choices[0].message.content or "")


def extract_preferences(user_input: str) -> dict:
    """Extract structured preferences from user input via LLM.

    Returns a dict with keys: destination, travelDates, people, budget, interests.
    Missing fields are None.
    """
    system_prompt = """你是一个旅行信息提取助手。从用户的旅行需求中提取结构化信息。

请从用户的输入中提取以下信息（JSON 格式输出，只输出 JSON，不要其他文字）：
{
  "destination": "目的地，如'云南'、'大理'、'日本'，没提到则为 null",
  "travelDates": "旅行时间，如'7月'、'2025年春节'、'3月中旬'，没提到则为 null",
  "people": "出行人数，如'2大1小'、'一个人'，没提到则为 null",
  "budget": "预算，如'5000'、'预算3000每人'，没提到则为 null",
  "interests": "兴趣偏好，如'亲子'、'爱吃辣'、'喜欢自然风光'，没提到则为 null"
}"""

    response = call_llm_simple(system_prompt, user_input, temperature=0.1)
    # Try to extract JSON from the response
    import re
    json_match = re.search(r'\{.*\}', response, re.DOTALL)
    if json_match:
        try:
            return json.loads(json_match.group())
        except json.JSONDecodeError:
            pass
    # Extraction failed — return a sentinel so caller can show a friendly message
    return {"_error": "请用更具体的描述重新告诉我"}


def generate_with_examples(system_prompt: str, user_message: str, examples: list[dict]) -> str:
    """Call LLM with example data to generate structured results.

    Used by tools that generate data from LLM knowledge rather than external APIs.
    """
    full_prompt = system_prompt + "\n\n参考示例数据（请参考格式，不要照抄内容）：\n" + json.dumps(examples, ensure_ascii=False, indent=2)
    return call_llm_simple(full_prompt, user_message)
