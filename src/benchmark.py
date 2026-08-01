"""Benchmark 核心执行引擎。"""

from __future__ import annotations

import logging
import random
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from .db_connector import DatabaseConnector

logger = logging.getLogger(__name__)


@dataclass
class QueryRecord:
    query_id: str
    database: str
    round_num: int
    start_time: str
    end_time: str
    elapsed_ms: float
    row_count: int
    result_hash: str | None
    success: bool
    error_message: str | None = None


@dataclass
class BenchmarkResult:
    database_name: str
    records: list[QueryRecord] = field(default_factory=list)


def _natural_query_key(path: Path) -> tuple[int, str]:
    suffix = path.stem.removeprefix("q")
    return (int(suffix), path.stem) if suffix.isdigit() else (10**9, path.stem)


def load_queries(queries_dir: str) -> dict[str, str]:
    path = Path(queries_dir)
    if not path.is_dir():
        raise FileNotFoundError(f"Queries directory not found: {queries_dir}")
    queries: dict[str, str] = {}
    for sql_file in sorted(path.glob("*.sql"), key=_natural_query_key):
        sql = sql_file.read_text(encoding="utf-8").strip()
        if not sql:
            raise ValueError(f"Empty query file: {sql_file}")
        queries[sql_file.stem] = sql
    if not queries:
        raise ValueError(f"No SQL files found in {queries_dir}")
    return queries


def run_round(
    connector: DatabaseConnector,
    queries: dict[str, str],
    round_num: int,
    db_name: str,
    timeout: int,
    *,
    randomize: bool = False,
    random_seed: int = 42,
) -> list[QueryRecord]:
    query_items = list(queries.items())
    if randomize:
        random.Random(random_seed + round_num).shuffle(query_items)
    records: list[QueryRecord] = []
    for query_id, sql in query_items:
        start = datetime.now(timezone.utc)
        result = connector.execute(sql, timeout)
        end = datetime.now(timezone.utc)
        record = QueryRecord(
            query_id=query_id,
            database=db_name,
            round_num=round_num,
            start_time=start.isoformat(timespec="milliseconds"),
            end_time=end.isoformat(timespec="milliseconds"),
            elapsed_ms=result.elapsed_ms,
            row_count=result.row_count,
            result_hash=result.result_hash,
            success=result.success,
            error_message=result.error,
        )
        status = "ok" if record.success else f"failed: {record.error_message}"
        logger.info(
            "[%s] %s %.2fms rows=%d %s",
            db_name,
            query_id,
            record.elapsed_ms,
            record.row_count,
            status,
        )
        records.append(record)
    return records


def run_benchmark(
    connector: DatabaseConnector,
    db_name: str,
    queries: dict[str, str],
    warmup: bool,
    warmup_rounds: int,
    test_rounds: int,
    timeout: int,
    *,
    randomize_query_order: bool = True,
    random_seed: int = 42,
) -> BenchmarkResult:
    result = BenchmarkResult(db_name)
    if warmup:
        for index in range(warmup_rounds):
            warmup_records = run_round(
                connector,
                queries,
                -(index + 1),
                db_name,
                timeout,
                randomize=randomize_query_order,
                random_seed=random_seed,
            )
            failures = [record for record in warmup_records if not record.success]
            if failures:
                failed = ", ".join(record.query_id for record in failures)
                raise RuntimeError(f"Warmup failed for {db_name}: {failed}")
    for round_num in range(1, test_rounds + 1):
        result.records.extend(
            run_round(
                connector,
                queries,
                round_num,
                db_name,
                timeout,
                randomize=randomize_query_order,
                random_seed=random_seed,
            )
        )
    return result
