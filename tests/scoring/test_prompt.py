from src.scoring.prompt import PRIORITIES, SCORE_TOOL, SYSTEM_PROMPT


def test_priorities_has_exactly_the_three_spec_values():
    assert PRIORITIES == ["A", "B", "C"]


def test_system_prompt_mentions_all_four_dimensions():
    for dimension in ["touchgo_interest", "event_importance", "source_confidence", "urgency"]:
        assert dimension in SYSTEM_PROMPT


def test_system_prompt_states_low_confidence_never_lowers_interest_rule():
    assert "JAMAIS" in SYSTEM_PROMPT
    assert "source_confidence" in SYSTEM_PROMPT


def test_score_tool_schema_has_required_fields():
    assert SCORE_TOOL["name"] == "score_news_item"
    properties = SCORE_TOOL["input_schema"]["properties"]
    assert set(properties) == {
        "touchgo_interest",
        "event_importance",
        "source_confidence",
        "urgency",
        "priority",
        "reasoning",
    }
    assert properties["priority"]["enum"] == PRIORITIES
    for dimension in ["touchgo_interest", "event_importance", "source_confidence", "urgency"]:
        assert properties[dimension]["minimum"] == 0
        assert properties[dimension]["maximum"] == 10
    required = SCORE_TOOL["input_schema"]["required"]
    assert set(required) == {
        "touchgo_interest",
        "event_importance",
        "source_confidence",
        "urgency",
        "priority",
        "reasoning",
    }
