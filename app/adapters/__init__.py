"""Platform adapters for MOJI AI Agent."""

from .base import BaseAdapter, PlatformMessage, MessageType, AttachmentType, Button, Card
# from .teams import TeamsAdapter  # Disabled for now - missing botbuilder dependency
# from .kakaotalk import KakaoTalkAdapter  # Disabled for now
from .webchat import WebChatAdapter

__all__ = [
    "BaseAdapter",
    "PlatformMessage",
    "MessageType",
    "AttachmentType",
    "Button",
    "Card",
    # "TeamsAdapter",  # Disabled for now
    # "KakaoTalkAdapter",  # Disabled for now
    "WebChatAdapter",
]