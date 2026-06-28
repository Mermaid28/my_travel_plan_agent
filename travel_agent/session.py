"""Session and Message data structures."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ToolCall:
    """Represents a tool call made by the LLM."""
    id: str
    name: str
    arguments: dict


@dataclass
class Message:
    """A single message in the conversation."""
    role: str  # 'user' | 'assistant' | 'tool' | 'system'
    content: str
    tool_calls: Optional[list[ToolCall]] = None
    tool_call_id: Optional[str] = None
    name: Optional[str] = None

    def to_openai(self) -> dict:
        """Convert to OpenAI API message format."""
        msg = {"role": self.role, "content": self.content}
        if self.tool_calls:
            msg["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.name,
                        "arguments": tc.arguments if isinstance(tc.arguments, str) else str(tc.arguments),
                    },
                }
                for tc in self.tool_calls
            ]
        if self.tool_call_id:
            msg["tool_call_id"] = self.tool_call_id
        if self.name:
            msg["name"] = self.name
        return msg


@dataclass
class UserPreferences:
    """User preferences extracted from input."""
    destination: Optional[str] = None
    travelDates: Optional[str] = None
    people: Optional[str] = None
    budget: Optional[str] = None
    interests: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "destination": self.destination,
            "travelDates": self.travelDates,
            "people": self.people,
            "budget": self.budget,
            "interests": self.interests,
        }

    @staticmethod
    def from_dict(d: dict) -> UserPreferences:
        return UserPreferences(
            destination=d.get("destination"),
            travelDates=d.get("travelDates"),
            people=d.get("people"),
            budget=d.get("budget"),
            interests=d.get("interests"),
        )


@dataclass
class Session:
    """Represents a single conversation session."""
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    messages: list[Message] = field(default_factory=list)
    userPreferences: UserPreferences = field(default_factory=UserPreferences)
    summary: Optional[str] = None
    writable: bool = False
