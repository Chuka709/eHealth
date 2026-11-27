"""The Claude reader (extraction/llm.py) against a fake SDK client - no network, no key."""

from types import SimpleNamespace
from typing import Any

import pytest

from labtrack.extraction.llm import (
    SYSTEM_PROMPT,
    AiDocument,
    AiReadError,
    AiReport,
    AiResult,
    AnthropicReader,
    to_read_document,
)

ANSWER = AiDocument(
    reports=[
        AiReport(
            lab_name="Lab",
            panel_name="Биохими",
            specimen="цус",
            collected_raw="2025-08-18",
            reported_raw=None,
            results=[
                AiResult(
                    raw_name="Креатинин",
                    raw_value="0.70",
                    raw_unit="мг/дл",
                    ref_text="0.7 - 1.2",
                    critical_text=None,
                    lab_flag=None,
                    page=2,
                ),
                AiResult(  # an empty row is dropped
                    raw_name=" ",
                    raw_value="1",
                    raw_unit=None,
                    ref_text=None,
                    critical_text=None,
                    lab_flag=None,
                    page=None,
                ),
            ],
        )
    ]
)


class _FakeMessages:
    def __init__(self, response: Any = None, error: Exception | None = None) -> None:
        self.response, self.error = response, error
        self.calls: list[dict[str, Any]] = []

    def parse(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        if self.error is not None:
            raise self.error
        return self.response


def _reader(messages: _FakeMessages) -> AnthropicReader:
    reader = AnthropicReader("test-key", "test-model")
    reader._client = SimpleNamespace(messages=messages)  # type: ignore[assignment]
    return reader


def _response(stop: str = "end_turn", parsed: AiDocument | None = ANSWER) -> Any:
    return SimpleNamespace(
        stop_reason=stop,
        parsed_output=parsed,
        usage=SimpleNamespace(input_tokens=1200, output_tokens=300),
    )


def test_the_answer_becomes_a_reading_without_a_person() -> None:
    document = to_read_document(ANSWER, "test-model")
    assert document.reader == "ai:test-model"
    assert (document.identity.family_name, document.identity.given_name) == (None, None)
    (row,) = document.reports[0].results
    assert (row.raw_name, row.raw_value, row.raw_unit, row.ref_text, row.page) == (
        "Креатинин",
        "0.70",
        "мг/дл",
        "0.7 - 1.2",
        2,
    )


def test_the_answers_shape_has_no_field_for_the_person() -> None:
    schema = AiDocument.model_json_schema()
    fields = set(schema["properties"])
    for definition in schema["$defs"].values():
        fields |= set(definition["properties"])
    assert fields == {
        "reports",
        "lab_name",
        "panel_name",
        "specimen",
        "collected_raw",
        "reported_raw",
        "results",
        "raw_name",
        "raw_value",
        "raw_unit",
        "ref_text",
        "critical_text",
        "lab_flag",
        "page",
    }


def test_a_read_sends_the_versioned_prompt_and_only_the_text() -> None:
    messages = _FakeMessages(_response())
    answer = _reader(messages).read("--- хуудас 1 ---\nКреатинин 0.70 мг/дл 0.7 - 1.2")
    (call,) = messages.calls
    assert call["model"] == "test-model"
    assert call["system"][0]["text"] == SYSTEM_PROMPT
    assert call["messages"] == [
        {"role": "user", "content": "--- хуудас 1 ---\nКреатинин 0.70 мг/дл 0.7 - 1.2"}
    ]
    assert call["output_format"] is AiDocument
    assert (answer.model, answer.input_tokens, answer.output_tokens) == ("test-model", 1200, 300)


@pytest.mark.parametrize(
    ("response", "code"),
    [
        (_response(stop="refusal"), "ai_refused"),
        (_response(stop="max_tokens"), "ai_incomplete"),
        (_response(parsed=None), "ai_empty"),
    ],
)
def test_no_usable_answer_is_a_code(response: Any, code: str) -> None:
    with pytest.raises(AiReadError) as caught:
        _reader(_FakeMessages(response)).read("x")
    assert caught.value.code == code


def test_the_api_unavailable_is_a_code_without_details() -> None:
    import anthropic  # noqa: PLC0415
    import httpx2  # noqa: PLC0415

    error = anthropic.APIConnectionError(request=httpx2.Request("POST", "https://api.example"))
    with pytest.raises(AiReadError) as caught:
        _reader(_FakeMessages(error=error)).read("x")
    assert caught.value.code == "ai_unavailable"
    assert caught.value.__cause__ is None


def test_the_prompt_forbids_guessing_and_advice() -> None:
    assert "ЗОХИОХГҮЙ" in SYSTEM_PROMPT
    assert "зөвлөгөө" in SYSTEM_PROMPT
