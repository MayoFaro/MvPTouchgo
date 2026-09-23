import ollama
import pytest

from src.scoring.client import (
    ScoringError,
    ScoringResult,
    parse_scoring_response,
    score_item,
)


class _FakeOllamaClient:
    def __init__(self, response=None, exception=None, fail_times=0):
        self._response = response
        self._exception = exception
        self._fail_times = fail_times
        self.calls = 0
        self.last_kwargs: dict | None = None

    async def chat(self, **kwargs):
        self.calls += 1
        self.last_kwargs = kwargs
        if self.calls <= self._fail_times:
            raise RuntimeError("simulated transient failure")
        if self._exception is not None:
            raise self._exception
        return self._response


def _valid_response() -> ollama.ChatResponse:
    return ollama.ChatResponse(
        model="test-model",
        message=ollama.Message(
            role="assistant",
            tool_calls=[
                ollama.Message.ToolCall(
                    function=ollama.Message.ToolCall.Function(
                        name="score_news_item",
                        arguments={
                            "touchgo_interest": 10,
                            "event_importance": 9,
                            "source_confidence": 3,
                            "urgency": 6,
                            "priority": "A",
                            "reasoning": "Sujet militaire majeur signalé par une source communautaire.",
                        },
                    )
                )
            ],
        ),
        done=True,
    )


def test_parse_scoring_response_extracts_the_tool_call():
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
    response = ollama.ChatResponse(
        model="test-model",
        message=ollama.Message(
            role="assistant",
            tool_calls=[
                ollama.Message.ToolCall(
                    function=ollama.Message.ToolCall.Function(
                        name="score_news_item",
                        arguments={
                            "touchgo_interest": 5,
                            "event_importance": 5,
                            "source_confidence": 5,
                            "urgency": 5,
                            "priority": "Z",
                            "reasoning": "test",
                        },
                    )
                )
            ],
        ),
        done=True,
    )

    with pytest.raises(ValueError):
        parse_scoring_response(response)


def test_parse_scoring_response_rejects_missing_numeric_field():
    response = ollama.ChatResponse(
        model="test-model",
        message=ollama.Message(
            role="assistant",
            tool_calls=[
                ollama.Message.ToolCall(
                    function=ollama.Message.ToolCall.Function(
                        name="score_news_item",
                        arguments={
                            "event_importance": 5,
                            "source_confidence": 5,
                            "urgency": 5,
                            "priority": "A",
                            "reasoning": "test",
                        },
                    )
                )
            ],
        ),
        done=True,
    )

    with pytest.raises(ValueError):
        parse_scoring_response(response)


def test_parse_scoring_response_rejects_out_of_range_score():
    response = ollama.ChatResponse(
        model="test-model",
        message=ollama.Message(
            role="assistant",
            tool_calls=[
                ollama.Message.ToolCall(
                    function=ollama.Message.ToolCall.Function(
                        name="score_news_item",
                        arguments={
                            "touchgo_interest": 99,
                            "event_importance": 5,
                            "source_confidence": 5,
                            "urgency": 5,
                            "priority": "A",
                            "reasoning": "test",
                        },
                    )
                )
            ],
        ),
        done=True,
    )

    with pytest.raises(ValueError):
        parse_scoring_response(response)


def test_parse_scoring_response_raises_when_no_tool_call():
    response = ollama.ChatResponse(
        model="test-model",
        message=ollama.Message(role="assistant", content="I won't call a tool."),
        done=True,
    )

    with pytest.raises(ValueError):
        parse_scoring_response(response)


@pytest.mark.asyncio
async def test_score_item_returns_result_on_first_success():
    client = _FakeOllamaClient(response=_valid_response())

    result = await score_item("Some title", "Some text", "community", client=client)

    assert result.priority == "A"
    assert client.calls == 1


@pytest.mark.asyncio
async def test_score_item_retries_once_then_succeeds():
    client = _FakeOllamaClient(response=_valid_response(), fail_times=1)

    result = await score_item("Some title", "Some text", "community", client=client)

    assert result.priority == "A"
    assert client.calls == 2


@pytest.mark.asyncio
async def test_score_item_raises_scoring_error_after_max_attempts():
    client = _FakeOllamaClient(fail_times=2)

    with pytest.raises(ScoringError):
        await score_item("Some title", "Some text", "community", client=client)

    assert client.calls == 2


@pytest.mark.asyncio
async def test_score_item_truncates_long_article_text():
    client = _FakeOllamaClient(response=_valid_response())
    long_text = "x" * 10_000

    await score_item("Some title", long_text, "community", client=client)

    sent_message = client.last_kwargs["messages"][-1]["content"]
    assert "x" * 4000 in sent_message
    assert "x" * 4001 not in sent_message


@pytest.mark.asyncio
async def test_score_item_includes_source_type_in_the_prompt():
    client = _FakeOllamaClient(response=_valid_response())

    await score_item("Some title", "Some text", "community", client=client)

    sent_message = client.last_kwargs["messages"][-1]["content"]
    assert "community" in sent_message


@pytest.mark.asyncio
async def test_score_item_includes_examples_block_when_provided():
    client = _FakeOllamaClient(response=_valid_response())

    await score_item(
        "Some title",
        "Some text",
        "community",
        examples="- Item priorité C donnée par le modèle ; retour humain : 🔥 (probablement sous-évalué).",
        client=client,
    )

    sent_message = client.last_kwargs["messages"][-1]["content"]
    assert "<exemples_feedback>" in sent_message
    assert "probablement sous-évalué" in sent_message


@pytest.mark.asyncio
async def test_score_item_omits_examples_block_when_not_provided():
    client = _FakeOllamaClient(response=_valid_response())

    await score_item("Some title", "Some text", "community", client=client)

    sent_message = client.last_kwargs["messages"][-1]["content"]
    assert "<exemples_feedback>" not in sent_message


@pytest.mark.asyncio
async def test_score_item_sends_system_prompt_as_first_message():
    client = _FakeOllamaClient(response=_valid_response())

    await score_item("Some title", "Some text", "community", client=client)

    messages = client.last_kwargs["messages"]
    assert messages[0]["role"] == "system"
    assert messages[-1]["role"] == "user"
