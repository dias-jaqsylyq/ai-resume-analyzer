from resume_analyzer import ids


def test_ulid_layout_and_known_value() -> None:
    value = ids.new_ulid(now_ms=0, randomness=bytes(10))
    assert value == "0" * 26
    assert ids.is_ulid(ids.new_ulid())


def test_ulids_sort_by_time() -> None:
    older = ids.new_ulid(now_ms=1_700_000_000_000, randomness=b"\xff" * 10)
    newer = ids.new_ulid(now_ms=1_700_000_000_001, randomness=bytes(10))
    assert older < newer


def test_is_ulid_rejects_other_strings() -> None:
    for value in [None, "", "an-1", "0" * 25, "0" * 27, "I" * 26, "../" + "0" * 23, 5]:
        assert not ids.is_ulid(value)
