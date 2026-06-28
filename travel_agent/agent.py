"""Agent orchestration — three-phase flow control."""

from __future__ import annotations

from travel_agent.llm import call_llm, extract_preferences
from travel_agent.prompts import PHASE1_SYSTEM_PROMPT, PHASE2_SYSTEM_PROMPT, PHASE3_SYSTEM_PROMPT
from travel_agent.registry import Tool, ToolRegistry
from travel_agent.session import Message, Session, UserPreferences
from travel_agent.tools.attractions import query_attractions
from travel_agent.tools.hotels import query_hotels
from travel_agent.tools.restaurants import query_restaurants
from travel_agent.tools.save_itinerary import save_itinerary as save_itinerary_impl
from travel_agent.tools.weather import query_weather


class TravelAgent:
    """Travel recommendation agent with three-phase lifecycle.

    Phase 1: Information gathering — collect destination + travel dates.
    Phase 2: Recommendation loop — LLM calls tools, generates itinerary.
    Phase 3: Follow-up — handle modifications, save, exit.
    """

    def __init__(self, session: Session):
        self.session = session
        self.registry = ToolRegistry()
        self._register_tools()

    def _register_tools(self) -> None:
        """Register all tools with the registry."""

        self.registry.register(Tool(
            name="query_weather",
            description="查询目的地天气情况。根据城市名称获取天气预报。",
            parameters={
                "type": "object",
                "properties": {
                    "city": {"type": "string", "description": "城市名称，如「北京」「大理」"},
                },
                "required": ["city"],
            },
            handler=query_weather,
        ))

        self.registry.register(Tool(
            name="query_attractions",
            description="查询目的地景点推荐。根据目的地和兴趣偏好获取景点列表。",
            parameters={
                "type": "object",
                "properties": {
                    "destination": {"type": "string", "description": "目的地，如「云南」「大理」"},
                    "interests": {"type": "string", "description": "兴趣偏好，如「亲子」「自然风光」"},
                },
                "required": ["destination"],
            },
            handler=query_attractions,
        ))

        self.registry.register(Tool(
            name="query_restaurants",
            description="查询目的地餐厅或美食推荐。根据地点和口味偏好获取餐厅列表。",
            parameters={
                "type": "object",
                "properties": {
                    "location": {"type": "string", "description": "地点，如「云南」「大理古城」"},
                    "taste": {"type": "string", "description": "口味偏好，如「爱吃辣」「清淡」"},
                },
                "required": ["location"],
            },
            handler=query_restaurants,
        ))

        self.registry.register(Tool(
            name="query_hotels",
            description="查询目的地酒店信息。根据城市名称获取酒店列表。",
            parameters={
                "type": "object",
                "properties": {
                    "city": {"type": "string", "description": "城市名称，如「北京」「大理」"},
                    "check_in": {"type": "string", "description": "入住日期（可选）"},
                    "check_out": {"type": "string", "description": "离店日期（可选）"},
                },
                "required": ["city"],
            },
            handler=query_hotels,
        ))

        # save_itinerary needs access to session.writable, so wrap it
        def save_itinerary_wrapper(
            content: str,
            filename: str = "",
            destination: str = "",
            travel_dates: str = "",
        ) -> str:
            return save_itinerary_impl(
                content=content,
                filename=filename,
                writable=self.session.writable,
                destination=destination,
                travel_dates=travel_dates,
            )

        self.registry.register(Tool(
            name="save_itinerary",
            description="保存当前行程到本地文件。用户说「保存」或「收藏」时调用。",
            parameters={
                "type": "object",
                "properties": {
                    "content": {"type": "string", "description": "行程内容（Markdown 格式）"},
                    "filename": {"type": "string", "description": "文件名（可选，不指定则自动生成）"},
                    "destination": {"type": "string", "description": "目的地，用于自动生成文件名"},
                    "travel_dates": {"type": "string", "description": "旅行时间，用于自动生成文件名"},
                },
                "required": ["content"],
            },
            handler=save_itinerary_wrapper,
        ))

    def process(self, user_input: str) -> str:
        """Process a user input and return the agent's response.

        Automatically detects current phase and routes accordingly.
        """
        if not user_input.strip():
            return "请输入旅行需求"

        self.session.messages.append(Message(role="user", content=user_input))

        # Phase detection
        prefs = self.session.userPreferences
        if not prefs.destination or not prefs.travelDates:
            return self._phase1()

        if self.session.summary is None:
            return self._phase2()

        return self._phase3()

    # ── Phase 1: Information Gathering ──────────────────────────────

    def _phase1(self) -> str:
        """Information gathering phase."""
        # Extract preferences from all user messages so far
        all_inputs = " ".join(
            m.content for m in self.session.messages if m.role == "user"
        )
        extracted = extract_preferences(all_inputs)

        # Check if extraction failed
        if extracted.get("_error"):
            msg = extracted["_error"]
            self.session.messages.append(Message(role="assistant", content=msg))
            return msg

        # Merge: new extraction overrides old, but keep existing if new is null
        existing = self.session.userPreferences
        self.session.userPreferences = UserPreferences(
            destination=extracted.get("destination") or existing.destination,
            travelDates=extracted.get("travelDates") or existing.travelDates,
            people=extracted.get("people") or existing.people,
            budget=extracted.get("budget") or existing.budget,
            interests=extracted.get("interests") or existing.interests,
        )

        # Check required fields
        prefs = self.session.userPreferences
        if prefs.destination and prefs.travelDates:
            # All required info present → move to phase 2
            return self._phase2()

        # Ask for missing info — let LLM generate a natural question
        recent_msgs = self.session.messages[-3:]  # last few messages for context
        system_msg = Message(role="system", content=PHASE1_SYSTEM_PROMPT)
        response = call_llm([system_msg] + recent_msgs, temperature=0.7)
        self.session.messages.append(response)
        return response.content

    # ── Phase 2: Recommendation Loop ────────────────────────────────

    def _build_phase2_context(self) -> list[Message]:
        """Build message list for phase 2 LLM calls."""
        prefs = self.session.userPreferences
        # Include a summary of known preferences as context
        pref_summary_parts = []
        if prefs.destination:
            pref_summary_parts.append(f"目的地：{prefs.destination}")
        if prefs.travelDates:
            pref_summary_parts.append(f"时间：{prefs.travelDates}")
        if prefs.people:
            pref_summary_parts.append(f"人数：{prefs.people}")
        if prefs.budget:
            pref_summary_parts.append(f"预算：{prefs.budget}")
        if prefs.interests:
            pref_summary_parts.append(f"偏好：{prefs.interests}")

        pref_context = "用户需求：" + "，".join(pref_summary_parts)

        return [
            Message(role="system", content=PHASE2_SYSTEM_PROMPT),
            Message(role="user", content=pref_context),
        ]

    def _phase2(self) -> str:
        """Recommendation loop: LLM calls tools → generates itinerary."""
        messages = self._build_phase2_context()
        openai_tools = self.registry.get_openai_tools()

        tool_rounds = 0
        max_tool_rounds = 8

        while tool_rounds <= max_tool_rounds:
            response = call_llm(messages, tools=openai_tools)

            if response.tool_calls:
                tool_rounds += 1
                # Append assistant message with tool_calls before tool results
                messages.append(response)
                # Execute all tool calls (may be parallel)
                for tc in response.tool_calls:
                    result = self.registry.execute(tc.name, tc.arguments if isinstance(tc.arguments, dict) else {})
                    messages.append(Message(
                        role="tool",
                        content=result,
                        tool_call_id=tc.id,
                        name=tc.name,
                    ))
            else:
                # Text response — this is the final itinerary
                itinerary = response.content
                self.session.messages.append(Message(role="assistant", content=itinerary))
                self._compress_to_summary(itinerary)
                return itinerary

        # Tool round limit reached — force output based on existing data
        force_msg = Message(role="user", content="已查询多轮，建议基于已有信息规划行程，直接输出结果。")
        messages.append(force_msg)
        response = call_llm(messages, tools=openai_tools)
        itinerary = response.content or "基于已有数据无法生成完整行程，请重新描述您的需求。"
        self.session.messages.append(Message(role="assistant", content=itinerary))
        self._compress_to_summary(itinerary)
        return itinerary

    def _compress_to_summary(self, itinerary: str) -> None:
        """After phase 2, compress conversation to summary and clear messages."""
        prefs = self.session.userPreferences
        summary_parts = [
            f"用户规划了{prefs.destination}旅行。",
        ]
        if prefs.travelDates:
            summary_parts.append(f"时间：{prefs.travelDates}。")
        if prefs.people:
            summary_parts.append(f"人数：{prefs.people}。")
        if prefs.budget:
            summary_parts.append(f"预算：{prefs.budget}。")

        # Truncate itinerary for summary
        itinerary_excerpt = itinerary[:300] if len(itinerary) > 300 else itinerary
        summary_parts.append(f"已输出行程概要：{itinerary_excerpt}")

        self.session.summary = "".join(summary_parts)

        # Clear old messages but keep the last assistant message for context
        self.session.messages = [
            m for m in self.session.messages
            if m.role == "assistant" and m.content
        ][-1:]  # keep only the last assistant message (the itinerary)

    # ── Phase 3: Follow-up ──────────────────────────────────────────

    def _phase3(self) -> str:
        """Follow-up interaction phase."""
        # Auto-handle save commands (more reliable than relying on LLM tool call)
        last_user_msg = self.session.messages[-1].content if self.session.messages else ""
        if any(kw in last_user_msg for kw in ("保存", "收藏")):
            return self._auto_save()

        messages = [
            Message(role="system", content=PHASE3_SYSTEM_PROMPT),
            Message(role="system", content=f"历史摘要：{self.session.summary}"),
        ]
        messages.extend(self.session.messages)

        openai_tools = self.registry.get_openai_tools()

        max_iterations = 10

        for _ in range(max_iterations):
            response = call_llm(messages, tools=openai_tools)

            if response.tool_calls:
                messages.append(response)
                for tc in response.tool_calls:
                    result = self.registry.execute(
                        tc.name,
                        tc.arguments if isinstance(tc.arguments, dict) else {},
                    )
                    messages.append(Message(
                        role="tool",
                        content=result,
                        tool_call_id=tc.id,
                        name=tc.name,
                    ))
            else:
                text = response.content

                # Check for global change marker
                if "__GLOBAL_CHANGE__" in text:
                    return self._handle_global_change(text)

                # Check for exit marker
                if "__EXIT__" in text:
                    return "再见！祝您旅途愉快！"

                # Local change or normal response
                self.session.messages.append(Message(role="assistant", content=text))
                return text

        return "处理超时，请重试。"

    def _auto_save(self) -> str:
        """Auto-save the last itinerary content when user says '保存'."""
        # Find the last assistant message with itinerary content
        last_itinerary = ""
        for m in reversed(self.session.messages):
            if m.role == "assistant" and len(m.content) > 50:
                last_itinerary = m.content
                break

        if not last_itinerary:
            return "没有找到可保存的行程内容，请先生成行程。"

        prefs = self.session.userPreferences
        result = save_itinerary_impl(
            content=last_itinerary,
            writable=self.session.writable,
            destination=prefs.destination or "",
            travel_dates=prefs.travelDates or "",
        )
        self.session.messages.append(Message(role="assistant", content=result))
        return result

    def _handle_global_change(self, text: str) -> str:
        """Handle global change: reset and restart phase 2."""
        # Parse new preferences from the marker
        # Format: __GLOBAL_CHANGE__: destination, travelDates, ...
        import re
        match = re.search(r"__GLOBAL_CHANGE__:\s*(.*)", text)
        if match:
            change_info = match.group(1).strip()
            parts = [p.strip() for p in change_info.split(",")]
            if len(parts) >= 1:
                self.session.userPreferences.destination = parts[0]
            if len(parts) >= 2:
                self.session.userPreferences.travelDates = parts[1]
            if len(parts) >= 3:
                self.session.userPreferences.interests = parts[2]

        # Reset state
        self.session.summary = None
        self.session.messages.clear()

        return self._phase2()

    # ── Public state check ──────────────────────────────────────────

    @property
    def is_in_phase1(self) -> bool:
        prefs = self.session.userPreferences
        return not prefs.destination or not prefs.travelDates

    @property
    def is_in_phase3(self) -> bool:
        return self.session.summary is not None
