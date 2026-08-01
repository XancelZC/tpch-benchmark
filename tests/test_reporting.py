import csv

import pytest

from src.benchmark import BenchmarkResult, QueryRecord
from src.reporter import compute_summary_metrics, generate_raw_csv
from src.stats import percentile


def record(db: str, qid: str, round_num: int, ms: float, success: bool = True):
    return QueryRecord(
        query_id=qid,
        database=db,
        round_num=round_num,
        start_time="2026-08-01T00:00:00.000+00:00",
        end_time="2026-08-01T00:00:00.001+00:00",
        elapsed_ms=ms,
        row_count=1,
        result_hash="abc" if success else None,
        success=success,
        error_message=None if success else "timeout",
    )


def test_percentile_rejects_invalid_percentile():
    with pytest.raises(ValueError):
        percentile([1, 2, 3], -1)
    with pytest.raises(ValueError):
        percentile([1, 2, 3], 101)


def test_raw_csv_contains_every_required_execution_field(tmp_path):
    result = BenchmarkResult(
        "db",
        records=[record("db", "q1", 1, 10), record("db", "q1", 2, 12)],
    )
    path = tmp_path / "raw.csv"
    generate_raw_csv({"db": result}, str(path))
    rows = list(csv.DictReader(path.open()))
    assert len(rows) == 2
    assert set(rows[0]) == {
        "database",
        "query_id",
        "round_num",
        "start_time",
        "end_time",
        "elapsed_ms",
        "row_count",
        "result_hash",
        "success",
        "error_message",
    }


def test_summary_reports_total_median_geomean_and_wins():
    base = BenchmarkResult(
        "A",
        records=[
            record("A", "q1", 1, 10),
            record("A", "q1", 2, 10),
            record("A", "q2", 1, 20),
            record("A", "q2", 2, 20),
        ],
    )
    other = BenchmarkResult(
        "B",
        records=[
            record("B", "q1", 1, 20),
            record("B", "q1", 2, 20),
            record("B", "q2", 1, 10),
            record("B", "q2", 2, 10),
        ],
    )
    summary = compute_summary_metrics(base, other)
    assert summary["total_time_ratio"] == pytest.approx(1.0)
    assert summary["median_speedup"] == pytest.approx(1.25)
    assert summary["geomean_speedup"] == pytest.approx(1.0)
    assert summary["base_wins"] == 1
    assert summary["other_wins"] == 1


def test_failed_queries_are_excluded_from_latency_but_counted_in_success_rate():
    base = BenchmarkResult(
        "A", records=[record("A", "q1", 1, 10), record("A", "q1", 2, 0, False)]
    )
    other = BenchmarkResult(
        "B", records=[record("B", "q1", 1, 20), record("B", "q1", 2, 20)]
    )
    summary = compute_summary_metrics(base, other)
    assert summary["total_time_ratio"] == pytest.approx(2.0)
    assert summary["base_success_rate"] == pytest.approx(0.5)
