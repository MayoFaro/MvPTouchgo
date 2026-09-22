# tests/classification/test_client.py
import pytest

from src.classification.client import (
    ClassificationError,
    ClassificationResult,
    classify_item,
    parse_classification_response,
)


class _FakeToolUseBlock:
    def __init__(self, name: str, input_data: dict):
        self.type = "tool_use"
        self.name = name
        self.input = input_data


class _FakeResponse:
    def __init__(self, content: list):
        self.content = content


class _FakeMessages:
    def __init__(self, response=None, exception=None, fail_times=0):
        self._response = response
        self._exception = exception
        self._fail_times = fail_times
        self.calls = 0
        self.last_kwargs: dict | None = None

    async def create(self, **kwargs):
        self.calls += 1
        self.last_kwargs = kwargs
        if self.calls <= self._fail_times:
            raise RuntimeError("simulated transient failure")
        if self._exception is not None:
            raise self._exception
        return self._response


class _FakeAnthropicClient:
    def __init__(self, response=None, exception=None, fail_times=0):
        self.messages = _FakeMessages(response=response, exception=exception, fail_times=fail_times)


def _valid_response() -> _FakeResponse:
    return _FakeResponse(
        [
            _FakeToolUseBlock(
                "classify_news_item",
                {
                    "primary_category": "MILITAIRE",
                    "secondary_categories": ["ACCIDENT_INCIDENT"],
                    "classification_confidence": 0.85,
                    "reasoning": "Accident impliquant un appareil militaire.",
                },
            )
        ]
    )


def test_parse_classification_response_extracts_the_tool_use_block():
    result = parse_classification_response(_valid_response())

    assert result == ClassificationResult(
        primary_category="MILITAIRE",
        secondary_categories=["ACCIDENT_INCIDENT"],
        classification_confidence=0.85,
        reasoning="Accident impliquant un appareil militaire.",
    )


def test_parse_classification_response_rejects_invalid_category():
    response = _FakeResponse(
        [
            _FakeToolUseBlock(
                "classify_news_item",
                {
                    "primary_category": "NOT_A_REAL_CATEGORY",
                    "secondary_categories": [],
                    "classification_confidence": 0.5,
                    "reasoning": "test",
                },
            )
        ]
    )

    with pytest.raises(ValueError):
        parse_classification_response(response)


def test_parse_classification_response_raises_when_no_tool_use_block():
    with pytest.raises(ValueError):
        parse_classification_response(_FakeResponse([]))


@pytest.mark.asyncio
async def test_classify_item_returns_result_on_first_success():
    client = _FakeAnthropicClient(response=_valid_response())

    result = await classify_item("Some title", "Some text", client=client)

    assert result.primary_category == "MILITAIRE"
    assert client.messages.calls == 1


@pytest.mark.asyncio
async def test_classify_item_retries_once_then_succeeds():
    client = _FakeAnthropicClient(response=_valid_response(), fail_times=1)

    result = await classify_item("Some title", "Some text", client=client)

    assert result.primary_category == "MILITAIRE"
    assert client.messages.calls == 2


@pytest.mark.asyncio
async def test_classify_item_raises_classification_error_after_max_attempts():
    client = _FakeAnthropicClient(fail_times=2)

    with pytest.raises(ClassificationError):
        await classify_item("Some title", "Some text", client=client)

    assert client.messages.calls == 2


@pytest.mark.asyncio
async def test_classify_item_truncates_long_article_text():
    client = _FakeAnthropicClient(response=_valid_response())
    long_text = "x" * 10_000

    await classify_item("Some title", long_text, client=client)

    sent_message = client.messages.last_kwargs["messages"][0]["content"]
    assert "x" * 4000 in sent_message
    assert "x" * 4001 not in sent_message


@pytest.mark.asyncio
async def test_classify_item_includes_examples_block_when_provided():
    client = _FakeAnthropicClient(response=_valid_response())

    await classify_item(
        "Some title",
        "Some text",
        examples="- Item classé COMMERCIAL par le modèle ; retour humain : hors périmètre Touch-Go.",
        client=client,
    )

    sent_message = client.messages.last_kwargs["messages"][0]["content"]
    assert "<exemples_feedback>" in sent_message
    assert "hors périmètre Touch-Go" in sent_message


@pytest.mark.asyncio
async def test_classify_item_omits_examples_block_when_not_provided():
    client = _FakeAnthropicClient(response=_valid_response())

    await classify_item("Some title", "Some text", client=client)

    sent_message = client.messages.last_kwargs["messages"][0]["content"]
    assert "<exemples_feedback>" not in sent_message
