"""scripts/benchmark.py: the numbers it reports for docs/metrics.md are computed correctly,
and the local benchmark runs the real handler without printing CV or report text."""

import importlib.util
from pathlib import Path

import pytest
from resume_analyzer.handlers import process_analysis

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "benchmark.py"
spec = importlib.util.spec_from_file_location("benchmark", SCRIPT)
benchmark = importlib.util.module_from_spec(spec)
spec.loader.exec_module(benchmark)


def test_percentile_is_nearest_rank() -> None:
    values = list(range(1, 21))  # 1..20
    assert benchmark.percentile(values, 50) == 10
    assert benchmark.percentile(values, 95) == 19
    assert benchmark.percentile(values, 100) == 20
    assert benchmark.percentile([7.0], 95) == 7.0
    with pytest.raises(ValueError):
        benchmark.percentile([], 50)


@pytest.fixture
def restore_handler(monkeypatch: pytest.MonkeyPatch):
    # run_local swaps module attributes; monkeypatch puts the originals back afterwards.
    for name in ("store", "textract_client", "cv_sha256"):
        monkeypatch.setattr(process_analysis, name, getattr(process_analysis, name))
    monkeypatch.delenv("BEDROCK_MODE", raising=False)


def test_local_benchmark_times_misses_and_hits(restore_handler, capsys) -> None:
    timings = benchmark.run_local(runs=5)

    assert len(timings["miss"]) == len(timings["hit"]) == 5
    assert all(t > 0 for t in timings["miss"] + timings["hit"])
    printed = "".join(capsys.readouterr())
    for line in benchmark.SYNTHETIC_CV_LINES[:4]:
        assert line not in printed


def test_mock_cost_is_mostly_textract() -> None:
    parts = benchmark.cost_per_cv(pages=1, mode="mock", lambda_ms=8000)

    assert parts["bedrock"] == 0
    assert parts["textract"] == pytest.approx(0.0015)
    assert sum(parts.values()) < 0.002  # $0.20 per 100 one-page CVs


def test_live_cost_adds_nova_tokens() -> None:
    mock = benchmark.cost_per_cv(pages=2, mode="mock", lambda_ms=8000)
    live = benchmark.cost_per_cv(
        pages=2, mode="live", input_tokens=3000, output_tokens=1000, lambda_ms=8000
    )

    assert live["bedrock"] == pytest.approx(3 * 0.00006 + 1 * 0.00024)
    assert sum(live.values()) - sum(mock.values()) == pytest.approx(live["bedrock"])


def test_input_token_estimate_grows_with_the_cv() -> None:
    small = benchmark.live_input_tokens(1000, 500)
    large = benchmark.live_input_tokens(5000, 500)
    assert large - small == 1000  # 4000 more chars at 4 chars per token
