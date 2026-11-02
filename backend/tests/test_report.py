import copy

import pytest
from resume_analyzer.report import InvalidReport, validate_report

VALID = {
    "ats_score": 72,
    "score_rationale": "Good  match\n on backend skills.",
    "matched_skills": ["Python", "python", " AWS ", ""],
    "missing_skills": ["Terraform"],
    "suggestions": [{"priority": "High", "section": "Skills", "advice": "Add Terraform."}],
    "summary": "Solid candidate.",
    "extra": "dropped",
}


def test_valid_report_is_normalised() -> None:
    report = validate_report(VALID)

    assert report == {
        "ats_score": 72,
        "score_rationale": "Good match on backend skills.",
        "matched_skills": ["Python", "AWS"],
        "missing_skills": ["Terraform"],
        "suggestions": [{"priority": "high", "section": "Skills", "advice": "Add Terraform."}],
        "summary": "Solid candidate.",
    }


def test_whole_number_float_score_is_accepted() -> None:
    assert validate_report({**VALID, "ats_score": 80.0})["ats_score"] == 80


@pytest.mark.parametrize(
    ("change", "field"),
    [
        ({"ats_score": 101}, "ats_score"),
        ({"ats_score": -1}, "ats_score"),
        ({"ats_score": "72"}, "ats_score"),
        ({"ats_score": True}, "ats_score"),
        ({"ats_score": 72.5}, "ats_score"),
        ({"summary": ""}, "summary"),
        ({"summary": "x" * 2001}, "summary"),
        ({"matched_skills": "Python"}, "matched_skills"),
        ({"matched_skills": [1]}, "matched_skills[0]"),
        ({"missing_skills": ["s"] * 31}, "missing_skills"),
        ({"suggestions": [{"priority": "urgent", "section": "a", "advice": "b"}]}, "priority"),
        ({"suggestions": [{"priority": "low", "section": "a"}]}, "advice"),
        ({"suggestions": ["text"]}, "suggestions[0]"),
    ],
)
def test_invalid_field_is_rejected(change: dict, field: str) -> None:
    with pytest.raises(InvalidReport, match=field.replace("[", r"\[").replace("]", r"\]")):
        validate_report({**VALID, **change})


def test_missing_field_is_rejected() -> None:
    data = copy.deepcopy(VALID)
    del data["summary"]
    with pytest.raises(InvalidReport, match="missing fields"):
        validate_report(data)


def test_error_message_never_contains_the_value() -> None:
    content = "Zebulon Quixote CV text"
    for bad in ({**VALID, "ats_score": content}, {**VALID, "summary": content * 200}):
        with pytest.raises(InvalidReport) as exc_info:
            validate_report(bad)
        assert "Zebulon" not in str(exc_info.value)
