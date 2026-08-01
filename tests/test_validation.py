from main import validate_result_hashes
from src.benchmark import BenchmarkResult, QueryRecord


def record(database: str, query_id: str, digest: str | None, success: bool = True):
    return QueryRecord(
        query_id=query_id,
        database=database,
        round_num=1,
        start_time="s",
        end_time="e",
        elapsed_ms=1,
        row_count=1,
        result_hash=digest,
        success=success,
        error_message=None if success else "timeout",
    )


def test_result_hash_validation_passes_when_all_databases_match():
    results = {
        "A": BenchmarkResult("A", [record("A", "q1", "same")]),
        "B": BenchmarkResult("B", [record("B", "q1", "same")]),
    }
    assert validate_result_hashes(results) == []


def test_result_hash_validation_detects_missing_successful_database_result():
    results = {
        "A": BenchmarkResult("A", [record("A", "q1", "same")]),
        "B": BenchmarkResult("B", [record("B", "q1", None, False)]),
    }
    errors = validate_result_hashes(results)
    assert len(errors) == 1
    assert "缺少成功结果" in errors[0]
    assert "B" in errors[0]


def test_result_hash_validation_detects_cross_database_mismatch():
    results = {
        "A": BenchmarkResult("A", [record("A", "q1", "a")]),
        "B": BenchmarkResult("B", [record("B", "q1", "b")]),
    }
    errors = validate_result_hashes(results)
    assert len(errors) == 1
    assert "跨库结果不一致" in errors[0]
