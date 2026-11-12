"""The AI worker's task: read the de-identified text with Claude (Phase 4.5; Q50).

Runs only on the AI worker (queue "ai"): no database, no field-encryption key, the API key
and one route out. Takes the text once from Valkey, asks the model, checks every row against
the text it sent (`verify`: a value or range not in it is `not_in_source`), and leaves the
answer - or an error code - under the request's nonce for the default worker, which polls
for it (this worker never starts anything else). Logs carry the id and a code.
"""

from collections.abc import Callable
from typing import Any

from structlog import get_logger

from labtrack.config import get_settings
from labtrack.extraction.isolated import to_json
from labtrack.extraction.llm import AiReader, AiReadError, AnthropicReader
from labtrack.extraction.verify import check_against_source
from labtrack.worker import ai_handoff

log = get_logger(__name__)


def _default_reader() -> AiReader | None:
    settings = get_settings()
    if settings.anthropic_api_key is None or not settings.extraction_model:
        return None
    return AnthropicReader(settings.anthropic_api_key.get_secret_value(), settings.extraction_model)


def read_with_ai(
    document_id: str, make_reader: Callable[[], AiReader | None] = _default_reader
) -> str:
    taken = ai_handoff.take_input(document_id)
    if taken is None:
        log.info("ai_read_done", document_id=document_id, result="ai_input_missing")
        return "ai_input_missing"  # expired, or taken already: nothing is sent, nothing left
    nonce, text = taken
    answer: dict[str, Any]
    if (reader := make_reader()) is None:
        answer = {"error": "ai_unconfigured"}
    else:
        try:
            read = reader.read(text)
            answer = {
                "document": to_json(check_against_source(read.document, text)),
                "model": read.model,
                "input_tokens": read.input_tokens,
                "output_tokens": read.output_tokens,
            }
        except AiReadError as exc:
            answer = {"error": exc.code}
        except Exception as exc:
            log.error(  # noqa: TRY400 - no traceback: it may quote the text
                "ai_read_failed", document_id=document_id, error=type(exc).__name__
            )
            answer = {"error": "ai_failed"}
    ai_handoff.put_output(document_id, nonce, answer)
    result = str(answer.get("error", "read"))
    log.info("ai_read_done", document_id=document_id, result=result)
    return result
