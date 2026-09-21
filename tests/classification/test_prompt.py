from src.classification.prompt import CATEGORIES, CLASSIFY_TOOL, SYSTEM_PROMPT


def test_categories_has_exactly_the_seven_spec_values():
    assert CATEGORIES == [
        "COMMERCIAL",
        "EMPLOI",
        "MILITAIRE",
        "REGLEMENTATION",
        "MEETING",
        "ACCIDENT_INCIDENT",
        "DIVERS",
    ]


def test_system_prompt_mentions_every_category():
    for category in CATEGORIES:
        assert category in SYSTEM_PROMPT


def test_system_prompt_states_the_divers_never_reject_rule():
    assert "DIVERS" in SYSTEM_PROMPT
    assert "JAMAIS" in SYSTEM_PROMPT.upper() or "JAMAIS" in SYSTEM_PROMPT


def test_classify_tool_schema_has_required_fields():
    assert CLASSIFY_TOOL["name"] == "classify_news_item"
    properties = CLASSIFY_TOOL["input_schema"]["properties"]
    assert set(properties) == {
        "primary_category",
        "secondary_categories",
        "classification_confidence",
        "reasoning",
    }
    assert properties["primary_category"]["enum"] == CATEGORIES
    assert properties["secondary_categories"]["items"]["enum"] == CATEGORIES
    required = CLASSIFY_TOOL["input_schema"]["required"]
    assert set(required) == {
        "primary_category",
        "secondary_categories",
        "classification_confidence",
        "reasoning",
    }
