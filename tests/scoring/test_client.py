import pytest

from src.scoring.client import (
    ScoringError,
    ScoringResult,
    parse_scoring_response,
    score_item,
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
                "score_news_item",
                {
                    "touchgo_interest": 10,
                    "event_importance": 9,
                    "source_confidence": 3,
                    "urgency": 6,
                    "priority": "A",
                    "reasoning": "Sujet militaire majeur signalé par une source communautaire.",
                },
            )
        ]
    )


def test_parse_scoring_response_extracts_the_tool_use_block():
    result = parse_scoring_response(_valid_response())

    assert result == ScoringResult(
        touchgo_interest=10,
        event_importance=9,
        source_confidence=3,
        urgency=6,
        priority="A",
        reasoning="Sujet militaire majeur signalé par une source communautaire.",
    )


def test_parse_scoring_response_rejects_invalid_priority():
    response = _FakeResponse(
        [
            _FakeToolUseBlock(
                "score_news_item",
                {
                    "touchgo_interest": 5,
                    "event_importance": 5,
                    "source_confidence": 5,
                    "urgency": 5,
                    "priority": "Z",
                    "reasoning": "test",
                },
            )
        ]
    )

    with pytest.raises(ValueError):
        parse_scoring_response(response)


def test_parse_scoring_response_rejects_missing_numeric_field():
    response = _FakeResponse(
        [
            _FakeToolUseBlock(
                "score_news_item",
                {
                    "event_importance": 5,
                    "source_confidence": 5,
                    "urgency": 5,
                    "priority": "A",
                    "reasoning": "test",
                },
            )
        ]
    )

    with pytest.raises(ValueError):
        parse_scoring_response(response)


def test_parse_scoring_response_rejects_out_of_range_score():
    response = _FakeResponse(
        [
            _FakeToolUseBlock(
                "score_news_item",
                {
                    "touchgo_interest": 99,
                    "event_importance": 5,
                    "source_confidence": 5,
                    "urgency": 5,
                    "priority": "A",
                    "reasoning": "test",
                },
            )
        ]
    )

    with pytest.raises(ValueError):
        parse_scoring_response(response)


def test_parse_scoring_response_raises_when_no_tool_use_block():
    with pytest.raises(ValueError):
        parse_scoring_response(_FakeResponse([]))


@pytest.mark.asyncio
async def test_score_item_returns_result_on_first_success():
    client = _FakeAnthropicClient(response=_valid_response())

    result = await score_item("Some title", "Some text", "community", client=client)

    assert result.priority == "A"
    assert client.messages.calls == 1


@pytest.mark.asyncio
async def test_score_item_retries_once_then_succeeds():
    client = _FakeAnthropicClient(response=_valid_response(), fail_times=1)

    result = await score_item("Some title", "Some text", "community", client=client)

    assert result.priority == "A"
    assert client.messages.calls == 2


@pytest.mark.asyncio
async def test_score_item_raises_scoring_error_after_max_attempts():
    client = _FakeAnthropicClient(fail_times=2)

    with pytest.raises(ScoringError):
        await score_item("Some title", "Some text", "community", client=client)

    assert client.messages.calls == 2


@pytest.mark.asyncio
async def test_score_item_truncates_long_article_text():
    client = _FakeAnthropicClient(response=_valid_response())
    long_text = "x" * 10_000

    await score_item("Some title", long_text, "community", client=client)

    sent_message = client.messages.last_kwargs["messages"][0]["content"]
    assert "x" * 4000 in sent_message
    assert "x" * 4001 not in sent_message


@pytest.mark.asyncio
async def test_score_item_includes_source_type_in_the_prompt():
    client = _FakeAnthropicClient(response=_valid_response())

    await score_item("Some title", "Some text", "community", client=client)

    sent_message = client.messages.last_kwargs["messages"][0]["content"]
    assert "community" in sent_message


@pytest.mark.asyncio
async def test_score_item_includes_examples_block_when_provided():
    client = _FakeAnthropicClient(response=_valid_response())

    await score_item(
        "Some title",
        "Some text",
        "community",
        examples="- Item priorité C donnée par le modèle ; retour humain : 🔥 (probablement sous-évalué).",
        client=client,
    )

    sent_message = client.messages.last_kwargs["messages"][0]["content"]
    assert "<exemples_feedback>" in sent_message
    assert "probablement sous-évalué" in sent_message


@pytest.mark.asyncio
async def test_score_item_omits_examples_block_when_not_provided():
    client = _FakeAnthropicClient(response=_valid_response())

    await score_item("Some title", "Some text", "community", client=client)

    sent_message = client.messages.last_kwargs["messages"][0]["content"]
    assert "<exemples_feedback>" not in sent_message
