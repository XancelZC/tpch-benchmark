#!/usr/bin/env python3
"""校验数据库表基数、关键谓词命中和版本信息。"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.config import Config
from src.db_connector import create_connector

TABLES = ["region", "nation", "supplier", "customer", "part", "partsupp", "orders", "lineitem"]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    parser.add_argument("--database", required=True)
    parser.add_argument("--manifest", default="data/load/manifest.json")
    args = parser.parse_args()

    config = Config.from_file(args.config)
    try:
        db = next(item for item in config.databases if item.name == args.database)
    except StopIteration as exc:
        raise ValueError(f"配置中不存在数据库：{args.database}") from exc
    manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
    connector = create_connector(db.type, db.host, db.port, db.database, db.user, db.password)
    output: dict[str, object] = {"database": db.name, "tables": {}}
    with connector:
        version = connector.execute("SELECT version()")
        if not version.success:
            raise RuntimeError(version.error)
        for table in TABLES:
            result = connector.execute(f"SELECT count(*) FROM {table}")
            if not result.success:
                raise RuntimeError(f"{table}: {result.error}")
            actual = int(result.scalar_value or -1)
            expected = int(manifest["files"][table]["rows"])
            if actual != expected:
                raise ValueError(f"{db.name}.{table} 行数 {actual}，预期 {expected}")
            output["tables"][table] = {
                "actual": actual,
                "expected": expected,
                "query_hash": result.result_hash,
            }
        probes = {
            "green_name": "SELECT count(*) FROM part WHERE lower(p_name) LIKE '%green%'",
            "forest_name": "SELECT count(*) FROM part WHERE lower(p_name) LIKE 'forest%'",
            "q8_type": "SELECT count(*) FROM part WHERE lower(p_type) = 'economy anodized steel'",
            "date_relation": "SELECT count(*) FROM lineitem WHERE l_commitdate < l_receiptdate",
        }
        output["probes"] = {}
        for name, sql in probes.items():
            result = connector.execute(sql)
            if not result.success:
                raise RuntimeError(f"{name}: {result.error}")
            actual = int(result.scalar_value or 0)
            if actual <= 0:
                raise ValueError(f"{db.name}.{name} 谓词命中数为 0")
            output["probes"][name] = actual
    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
