"""The analysis report: JSON contract between the model, the backend and the frontend.

``REPORT_SCHEMA`` is given to the model as the input schema of the ``submit_report`` tool, and
``validate_report`` checks whatever comes back, because a model can still return wrong types,
missing fields or out-of-range values. Contract: docs/02-architecture.md ("Report JSON").

Error messages name the field and the rule only, never the value: the value is model output,
and exception messages end up in logs.
"""

from __future__ import annotations

from typing import Any

PRIORITIES = ("high", "medium", "low")
MAX_SKILLS = 30
MAX_SUGGESTIONS = 10
MAX_SHORT_TEXT = 200
MAX_LONG_TEXT = 2000

REPORT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "ats_score": {
            "type": "integer",
            "minimum": 0,
            "maximum": 100,
            "description": "How well the resume matches the job description, 0-100.",
        },
        "score_rationale": {
            "type": "string",
            "description": "Two or three sentences explaining the score.",
        },
        "matched_skills": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Skills from the job description that the resume shows.",
        },
        "missing_skills": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Skills from the job description that the resume does not show.",
        },
        "suggestions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "priority": {"type": "string", "enum": list(PRIORITIES)},
                    "section": {"type": "string", "description": "Resume section to change."},
                    "advice": {"type": "string", "description": "One concrete change."},
                },
                "required": ["priority", "section", "advice"],
            },
        },
        "summary": {"type": "string", "description": "One paragraph overall assessment."},
    },
    "required": [
        "ats_score",
        "score_rationale",
        "matched_skills",
        "missing_skills",
        "suggestions",
        "summary",
    ],
}


class InvalidReport(ValueError):
    """The model output does not match the report contract."""


def _text(value: Any, field: str, max_len: int, *, allow_empty: bool = False) -> str:
    if not isinstance(value, str):
        raise InvalidReport(f"{field}: expected a string")
    value = " ".join(value.split())
    if not value and not allow_empty:
        raise InvalidReport(f"{field}: must not be empty")
    if len(value) > max_len:
        raise InvalidReport(f"{field}: longer than {max_len} characters")
    return value


def _skills(value: Any, field: str) -> list[str]:
    if not isinstance(value, list):
        raise InvalidReport(f"{field}: expected a list")
    if len(value) > MAX_SKILLS:
        raise InvalidReport(f"{field}: more than {MAX_SKILLS} items")
    skills: list[str] = []
    seen: set[str] = set()
    for i, item in enumerate(value):
        skill = _text(item, f"{field}[{i}]", MAX_SHORT_TEXT, allow_empty=True)
        if skill and skill.lower() not in seen:  # drop blanks and case-insensitive duplicates
            seen.add(skill.lower())
            skills.append(skill)
    return skills


def validate_report(data: Any) -> dict[str, Any]:
    """Return a normalised copy of ``data`` or raise ``InvalidReport``.

    Normalising: whitespace collapsed, duplicate/blank skills dropped, a whole-number float
    score (e.g. ``72.0``) accepted as an int, unknown keys dropped.
    """
    if not isinstance(data, dict):
        raise InvalidReport("report: expected an object")
    missing = [k for k in REPORT_SCHEMA["required"] if k not in data]
    if missing:
        raise InvalidReport(f"report: missing fields {missing}")

    score = data["ats_score"]
    if isinstance(score, float) and score.is_integer():
        score = int(score)
    if isinstance(score, bool) or not isinstance(score, int):
        raise InvalidReport("ats_score: expected an integer")
    if not 0 <= score <= 100:
        raise InvalidReport("ats_score: out of range 0-100")

    suggestions = data["suggestions"]
    if not isinstance(suggestions, list):
        raise InvalidReport("suggestions: expected a list")
    if len(suggestions) > MAX_SUGGESTIONS:
        raise InvalidReport(f"suggestions: more than {MAX_SUGGESTIONS} items")
    clean_suggestions = []
    for i, item in enumerate(suggestions):
        field = f"suggestions[{i}]"
        if not isinstance(item, dict):
            raise InvalidReport(f"{field}: expected an object")
        priority = item.get("priority")
        if not isinstance(priority, str) or priority.lower() not in PRIORITIES:
            raise InvalidReport(f"{field}.priority: expected one of {list(PRIORITIES)}")
        clean_suggestions.append(
            {
                "priority": priority.lower(),
                "section": _text(item.get("section"), f"{field}.section", MAX_SHORT_TEXT),
                "advice": _text(item.get("advice"), f"{field}.advice", MAX_LONG_TEXT),
            }
        )

    return {
        "ats_score": score,
        "score_rationale": _text(data["score_rationale"], "score_rationale", MAX_LONG_TEXT),
        "matched_skills": _skills(data["matched_skills"], "matched_skills"),
        "missing_skills": _skills(data["missing_skills"], "missing_skills"),
        "suggestions": clean_suggestions,
        "summary": _text(data["summary"], "summary", MAX_LONG_TEXT),
    }
