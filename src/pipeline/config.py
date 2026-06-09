"""Config / secrets. Keys are read from .env — never hard-code them."""
from __future__ import annotations

import os

from dotenv import load_dotenv

load_dotenv()

# LLM provider (default: Anthropic Claude).
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")

# Web search / research API key. Provider TBD (Tavily recommended).
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY")
