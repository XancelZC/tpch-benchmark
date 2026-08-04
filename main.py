#!/usr/bin/env python3
"""MatrixBench：多数据库查询执行、校验与结果汇总工具。"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import platform
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from src.benchmark import BenchmarkResult, load_queries, run_benchmark
from src.config import Config
from src.db_connector import create_connector
from src.reporter import (
    compare_results,
    compute_summary_metrics,
    generate_raw_csv,
    generate_report,
    generate_summary_csv,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("matrixbench")


def _command_output(command: list[str]) -> str:
    try:
        return subprocess.run(
            command, capture_output=True, text=True, check=True, timeout=10
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return "unknown"


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    digest.update(path.read_bytes())
    return digest.hexdigest()


def _container_metadata(container: str | None) -> dict[str, object]:
    """采集可选的 Docker 容器架构、镜像和资源限制。"""
    if not container:
        return {}
    template = (
        "{{.Config.Image}}|{{.HostConfig.NanoCpus}}|"
        "{{.HostConfig.Memory}}|{{.HostConfig.MemorySwap}}"
    )
    inspect = _command_output(["docker", "inspect", container, "--format", template])
    architecture = _command_output(["docker", "exec", container, "uname", "-m"])
    if inspect == "unknown":
        return {"container": container, "architecture": architecture}
    image, nano_cpus, memory, memory_swap = inspect.split("|", 3)
    return {
        "container": container,
        "image": image,
        "architecture": architecture,
        "cpu_limit": int(nano_cpus) / 1_000_000_000 if nano_cpus.isdigit() else nano_cpus,
        "memory_limit_bytes": int(memory) if memory.isdigit() else memory,
        "memory_swap_bytes": int(memory_swap) if memory_swap.isdigit() else memory_swap,
    }


def build_metadata(config: Config, run_id: str) -> dict[str, object]:
    """动态采集本次运行的环境信息。"""
    manifest_path = Path("data/load/manifest.json")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    return {
        "run_id": run_id,
        "started_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "os": platform.platform(),
        "machine": platform.machine(),
        "processor": platform.processor(),
        "python": platform.python_version(),
        "docker_server_arch": _command_output(
            ["docker", "version", "--format", "{{.Server.Arch}}"]
        ),
        "data_generator": (
            f"{manifest['generator']} {manifest['generator_reported_version']} "
            f"({manifest['generator_commit']})"
        ),
        "scale_factor": manifest["scale_factor"],
        "data_manifest": str(manifest_path),
        "test_rounds": config.benchmark.test_rounds,
        "warmup_rounds": config.benchmark.warmup_rounds,
        "timeout_seconds": config.benchmark.timeout_seconds,
        "concurrency": config.benchmark.concurrency,
        "timing_semantics": "time-to-last-row",
        "query_order": "deterministic-randomized"
        if config.benchmark.randomize_query_order
        else "natural",
        "disclaimer": manifest["disclaimer"],
        "schema_profile": "indexed",
        "query_sha256": {
            path.name: _file_sha256(path)
            for path in sorted(Path(config.benchmark.queries_dir).glob("*.sql"))
        },
        "databases": [],
    }


def validate_result_hashes(results: dict[str, BenchmarkResult]) -> list[str]:
    """校验每条查询在各库每轮的结果摘要是否一致。"""
    mismatches: list[str] = []
    by_query: dict[str, dict[str, set[str]]] = {}
    for db_name, result in results.items():
        for record in result.records:
            if record.success and record.result_hash:
                by_query.setdefault(record.query_id, {}).setdefault(db_name, set()).add(
                    record.result_hash
                )
    database_names = set(results)
    all_query_ids = {
        record.query_id for result in results.values() for record in result.records
    }
    for query_id in sorted(all_query_ids):
        database_hashes = by_query.get(query_id, {})
        missing = database_names - set(database_hashes)
        if missing:
            mismatches.append(f"{query_id} 缺少成功结果：{sorted(missing)}")
            continue
        unstable = {name: values for name, values in database_hashes.items() if len(values) != 1}
        if unstable:
            mismatches.append(f"{query_id} 单库多轮结果不稳定：{unstable}")
            continue
        unique_hashes = {next(iter(values)) for values in database_hashes.values()}
        if len(unique_hashes) != 1:
            mismatches.append(f"{query_id} 跨库结果不一致：{database_hashes}")
    return mismatches


def main() -> None:
    parser = argparse.ArgumentParser(description="MatrixBench 多数据库查询测试工具")
    parser.add_argument("-c", "--config", default="config.yaml", help="配置文件路径")
    parser.add_argument(
        "--allow-result-mismatch",
        action="store_true",
        help="仅用于诊断：结果摘要不一致时仍生成报告",
    )
    args = parser.parse_args()

    config = Config.from_file(args.config)
    queries = load_queries(config.benchmark.queries_dir)
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_dir = Path(config.output.output_dir) / run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    metadata = build_metadata(config, run_id)
    results: dict[str, BenchmarkResult] = {}

    for db_config in config.databases:
        logger.info("开始测试 %s", db_config.name)
        connector = create_connector(
            db_config.type,
            db_config.host,
            db_config.port,
            db_config.database,
            db_config.user,
            db_config.password,
        )
        with connector:
            version = connector.execute("SELECT version()")
            if not version.success:
                raise RuntimeError(f"{db_config.name} 版本查询失败：{version.error}")
            metadata["databases"].append(
                {
                    "name": db_config.name,
                    "type": db_config.type,
                    "host": db_config.host,
                    "port": db_config.port,
                    "version": version.scalar_value,
                    "version_hash": version.result_hash,
                    **_container_metadata(db_config.container),
                }
            )
            connector.execute_params(db_config.params)
            results[db_config.name] = run_benchmark(
                connector,
                db_config.name,
                queries,
                config.benchmark.warmup,
                config.benchmark.warmup_rounds,
                config.benchmark.test_rounds,
                config.benchmark.timeout_seconds,
                randomize_query_order=config.benchmark.randomize_query_order,
                random_seed=config.benchmark.random_seed,
            )

    raw_path = run_dir / config.output.raw_csv
    generate_raw_csv(results, str(raw_path))
    failures = [
        record
        for result in results.values()
        for record in result.records
        if not record.success
    ]
    mismatches = validate_result_hashes(results)
    metadata["result_mismatches"] = mismatches
    metadata["failure_count"] = len(failures)

    base_name = config.databases[0].name
    base_result = results[base_name]
    summaries: list[dict[str, object]] = []
    all_comparisons: list[dict[str, object]] = []
    for db_config in config.databases[1:]:
        other_result = results[db_config.name]
        summaries.append(compute_summary_metrics(base_result, other_result))
        all_comparisons.extend(compare_results(base_result, other_result))

    generate_summary_csv(
        summaries,
        all_comparisons,
        str(run_dir / config.output.summary_csv),
    )
    (run_dir / config.output.metadata_file).write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    generate_report(
        results,
        summaries,
        all_comparisons,
        metadata,
        str(run_dir / config.output.report_file),
    )
    latest = Path(config.output.output_dir) / "LATEST"
    latest.write_text(run_id + "\n", encoding="utf-8")
    logger.info("运行产物：%s", run_dir)

    # 自动生成图表（独立脚本，失败不影响主结果）
    try:
        chart_env = os.environ.copy()
        chart_env.pop("PYTHONPATH", None)
        subprocess.run(
            [sys.executable, str(Path(__file__).parent / "tools" / "make_charts.py"), str(run_dir)],
            check=False,
            capture_output=True,
            timeout=120,
            env=chart_env,
        )
        chart_dir = run_dir / "charts"
        if chart_dir.is_dir() and any(chart_dir.glob("*.png")):
            logger.info("图表已生成：%s", chart_dir)
        else:
            logger.warning("图表生成未产出文件，可手动执行 tools/make_charts.py %s", run_dir)
    except (OSError, subprocess.SubprocessError) as exc:
        logger.warning("图表自动生成失败（不影响结果）：%s", exc)

    if (failures or mismatches) and not args.allow_result_mismatch:
        if failures:
            logger.error("存在 %d 条失败记录", len(failures))
        if mismatches:
            logger.error("结果正确性校验失败：\n%s", "\n".join(mismatches))
        sys.exit(2)


if __name__ == "__main__":
    main()
