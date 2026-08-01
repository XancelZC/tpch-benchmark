"""配置文件解析与校验。"""

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

SUPPORTED_DATABASE_TYPES = {"postgresql", "mysql", "ymatrix", "greenplum"}


def _expand_env(value: str) -> str:
    """展开配置中的 ${ENV_NAME}，缺少变量时保留原文本以便校验阶段发现。"""
    pattern = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")
    return pattern.sub(lambda match: os.environ.get(match.group(1), match.group(0)), value)


@dataclass(frozen=True)
class DatabaseConfig:
    name: str
    type: str
    host: str = "localhost"
    port: int = 5432
    database: str = "tpch"
    user: str = "benchmark"
    password: str = ""
    container: str | None = None
    params: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "DatabaseConfig":
        if not isinstance(data, dict):
            raise TypeError("Each database entry must be a mapping")
        for required in ("name", "type"):
            if not data.get(required):
                raise ValueError(f"Database field '{required}' is required")
        db_type = str(data["type"]).lower()
        if db_type not in SUPPORTED_DATABASE_TYPES:
            raise ValueError(
                f"Unsupported database type: {db_type}. "
                f"Supported: {sorted(SUPPORTED_DATABASE_TYPES)}"
            )
        default_port = 3306 if db_type == "mysql" else 5432
        port = data.get("port", default_port)
        if not isinstance(port, int) or not 1 <= port <= 65535:
            raise ValueError(f"Invalid port for database {data['name']}: {port}")
        params = data.get("params", [])
        if not isinstance(params, list) or not all(isinstance(p, str) for p in params):
            raise ValueError(f"params for database {data['name']} must be a list of SQL strings")
        return cls(
            name=str(data["name"]),
            type=db_type,
            host=str(data.get("host", "localhost")),
            port=port,
            database=str(data.get("database", "tpch")),
            user=str(data.get("user", "benchmark")),
            password=_expand_env(str(data.get("password", ""))),
            container=str(data["container"]) if data.get("container") else None,
            params=params,
        )


@dataclass(frozen=True)
class BenchmarkConfig:
    queries_dir: str = "./queries"
    warmup: bool = True
    warmup_rounds: int = 1
    test_rounds: int = 5
    timeout_seconds: int = 300
    concurrency: int = 1
    randomize_query_order: bool = True
    random_seed: int = 42

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "BenchmarkConfig":
        if not isinstance(data, dict):
            raise TypeError("benchmark must be a mapping")
        values = {
            "warmup_rounds": data.get("warmup_rounds", 1),
            "test_rounds": data.get("test_rounds", 5),
            "timeout_seconds": data.get("timeout_seconds", 300),
            "concurrency": data.get("concurrency", 1),
        }
        for name, value in values.items():
            if not isinstance(value, int) or value < 1:
                raise ValueError(f"benchmark.{name} must be a positive integer")
        if values["concurrency"] != 1:
            raise ValueError(
                "Only concurrency=1 is implemented. Concurrent mode requires "
                "independent connections and a separate throughput methodology."
            )
        return cls(
            queries_dir=str(data.get("queries_dir", "./queries")),
            warmup=bool(data.get("warmup", True)),
            warmup_rounds=values["warmup_rounds"],
            test_rounds=values["test_rounds"],
            timeout_seconds=values["timeout_seconds"],
            concurrency=values["concurrency"],
            randomize_query_order=bool(data.get("randomize_query_order", True)),
            random_seed=int(data.get("random_seed", 42)),
        )


@dataclass(frozen=True)
class OutputConfig:
    output_dir: str = "./results/latest"
    raw_csv: str = "raw_records.csv"
    summary_csv: str = "comparison_summary.csv"
    report_file: str = "report.md"
    metadata_file: str = "metadata.json"

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "OutputConfig":
        if not isinstance(data, dict):
            raise TypeError("output must be a mapping")
        return cls(
            output_dir=str(data.get("output_dir", "./results/latest")),
            raw_csv=str(data.get("raw_csv", "raw_records.csv")),
            summary_csv=str(data.get("summary_csv", "comparison_summary.csv")),
            report_file=str(data.get("report_file", "report.md")),
            metadata_file=str(data.get("metadata_file", "metadata.json")),
        )


@dataclass(frozen=True)
class Config:
    databases: list[DatabaseConfig]
    benchmark: BenchmarkConfig
    output: OutputConfig

    @classmethod
    def from_file(cls, path: str) -> "Config":
        config_path = Path(path)
        try:
            raw = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        except yaml.YAMLError as exc:
            raise ValueError(f"Invalid YAML in {path}: {exc}") from exc
        if raw is None:
            raise ValueError(f"Configuration file is empty: {path}")
        if not isinstance(raw, dict):
            raise TypeError("Top-level configuration must be a mapping")
        raw_databases = raw.get("databases", [])
        if not isinstance(raw_databases, list) or len(raw_databases) < 2:
            raise ValueError("config must contain at least 2 databases")
        databases = [DatabaseConfig.from_dict(item) for item in raw_databases]
        names = [db.name for db in databases]
        if len(names) != len(set(names)):
            raise ValueError("Database names must be unique")
        return cls(
            databases=databases,
            benchmark=BenchmarkConfig.from_dict(raw.get("benchmark", {})),
            output=OutputConfig.from_dict(raw.get("output", {})),
        )
