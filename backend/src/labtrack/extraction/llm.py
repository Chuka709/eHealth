"""Reading de-identified report text with Claude (Phase 4.5; docs/05; Q50).

Used only for a text PDF of no known layout, only with the person's consent, and only on the
text `deidentify` left (never a file, scan or photo). The answer is raw text per row, as
printed - exactly what a local reader returns - so `core` turns it into numbers and checks
it the same way (rule 6), and it is a draft (rule 4). The model and the key come from the
environment (rule 11); the prompt is versioned (`prompts/v1.md`).

Runs on the AI worker only (queue "ai"): the one process with the key and a route out, and
without the database or the field-encryption key.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Final, Protocol

from pydantic import BaseModel, ConfigDict

from labtrack.extraction.types import PrintedIdentity, ReadDocument, ReadReport, ReadResult

PROMPT_VERSION: Final = "v1"
SYSTEM_PROMPT: Final = (Path(__file__).parent / "prompts" / f"{PROMPT_VERSION}.md").read_text(
    encoding="utf-8"
)
MAX_OUTPUT_TOKENS: Final = 16_000


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AiResult(_Strict):
    raw_name: str
    raw_value: str
    raw_unit: str | None
    ref_text: str | None
    critical_text: str | None
    lab_flag: str | None
    page: int | None


class AiReport(_Strict):
    lab_name: str | None
    panel_name: str | None
    specimen: str | None
    collected_raw: str | None
    reported_raw: str | None
    results: list[AiResult]


class AiDocument(_Strict):
    """The answer's shape (structured output): no field for the person - they are not in it."""

    reports: list[AiReport]


@dataclass(frozen=True, slots=True)
class AiAnswer:
    document: ReadDocument
    model: str
    input_tokens: int
    output_tokens: int


class AiReadError(Exception):
    """The model gave no usable answer: `code` only (refused, cut short, empty, unavailable)."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class AiReader(Protocol):
    def read(self, text: str) -> AiAnswer: ...


def to_read_document(answer: AiDocument, model: str) -> ReadDocument:
    """As a local reader's reading; no printed identity (it was removed before sending)."""
    return ReadDocument(
        reader=f"ai:{model}"[:80],
        identity=PrintedIdentity(),
        reports=tuple(
            ReadReport(
                lab_name=r.lab_name,
                panel_name=r.panel_name,
                specimen=r.specimen,
                collected_raw=r.collected_raw,
                reported_raw=r.reported_raw,
                results=tuple(
                    ReadResult(
                        raw_name=x.raw_name,
                        raw_value=x.raw_value,
                        raw_unit=x.raw_unit,
                        ref_text=x.ref_text,
                        lab_flag=x.lab_flag,
                        # a page it did not name, or one out of range, stays unknown
                        page=x.page if x.page is not None and 1 <= x.page <= 50 else None,  # noqa: PLR2004
                        snippet="",  # set from the sent text by verify, never by the model
                        critical_text=x.critical_text,
                    )
                    for x in r.results
                    if x.raw_name.strip() and x.raw_value.strip()
                ),
            )
            for r in answer.reports
        ),
    )


class AnthropicReader:
    """The real reader: Messages API with a structured output; the SDK retries 429/5xx."""

    def __init__(self, api_key: str, model: str, *, timeout: float = 50.0) -> None:
        import logging  # noqa: PLC0415

        import anthropic  # noqa: PLC0415 - only the AI worker needs the SDK loaded

        # the SDK logs requests at debug level: never on this worker (they carry the text)
        for name in ("anthropic", "httpx", "httpx2", "httpcore"):
            logging.getLogger(name).setLevel(logging.WARNING)
        self._anthropic = anthropic
        # one retry: two tries of 50 s stay inside the task's 150 s soft limit
        self._client = anthropic.Anthropic(api_key=api_key, timeout=timeout, max_retries=1)
        self._model = model

    def read(self, text: str) -> AiAnswer:
        anthropic = self._anthropic
        try:
            response = self._client.messages.parse(
                model=self._model,
                max_tokens=MAX_OUTPUT_TOKENS,
                system=[
                    {"type": "text", "text": SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}
                ],
                messages=[{"role": "user", "content": text}],
                output_format=AiDocument,
            )
        except (anthropic.RateLimitError, anthropic.InternalServerError):
            raise AiReadError("ai_unavailable") from None  # after the SDK's own retries
        except anthropic.APIStatusError:
            raise AiReadError("ai_rejected") from None  # a request it will not take
        except anthropic.APIConnectionError:
            raise AiReadError("ai_unavailable") from None
        if response.stop_reason == "refusal":
            raise AiReadError("ai_refused")
        if response.stop_reason == "max_tokens":
            raise AiReadError("ai_incomplete")
        parsed = response.parsed_output
        if parsed is None:
            raise AiReadError("ai_empty")
        return AiAnswer(
            document=to_read_document(parsed, self._model),
            model=self._model,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
        )
