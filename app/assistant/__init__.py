"""Read-only article assistant: query layer and model-client seam."""

from app.assistant.client import (
    AssistantUnavailable,
    AzureOpenAIClient,
    LLMClient,
    LLMResponse,
    OpenAICompatibleClient,
    ToolCall,
    get_client,
)
from app.assistant.prompts import build_system_prompt
from app.assistant.service import AssistantResult, ask
from app.assistant.tools import (
    MAX_ROWS_SCANNED,
    MAX_ROWS_TO_MODEL,
    ToolResult,
    artikel_details,
    artikel_suchen,
    artikel_zaehlen,
    datenstand,
    einheiten_auflisten,
    gruppen_auflisten,
    resolve_current_snapshot,
)
from app.assistant.verification import verify_numbers

__all__ = [
    "MAX_ROWS_SCANNED",
    "MAX_ROWS_TO_MODEL",
    "AssistantResult",
    "AssistantUnavailable",
    "AzureOpenAIClient",
    "LLMClient",
    "LLMResponse",
    "OpenAICompatibleClient",
    "ToolCall",
    "ToolResult",
    "artikel_details",
    "artikel_suchen",
    "artikel_zaehlen",
    "ask",
    "build_system_prompt",
    "datenstand",
    "einheiten_auflisten",
    "get_client",
    "gruppen_auflisten",
    "resolve_current_snapshot",
    "verify_numbers",
]
