#!/usr/bin/env python3
"""清理 dbgen 尾分隔符并生成数据清单。"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

TABLES = ["region", "nation", "supplier", "customer", "part", "partsupp", "orders", "lineitem"]
EXPECTED_FIXED = {"region": 5, "nation": 25}
EXPECTED_SCALED = {
    "supplier": 10_000,
    "customer": 150_000,
    "part": 200_000,
    "partsupp": 800_000,
    "orders": 1_500_000,
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def row_count(path: Path) -> int:
    with path.open("rb") as handle:
        return sum(1 for _ in handle)


def expected_rows(table: str, scale_factor: float) -> int | None:
    if table in EXPECTED_FIXED:
        return EXPECTED_FIXED[table]
    if table in EXPECTED_SCALED:
        return round(EXPECTED_SCALED[table] * scale_factor)
    # lineitem 行数由每订单明细数随机决定，只校验合理范围。
    return None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True)
    parser.add_argument("--load-dir", required=True)
    parser.add_argument("--scale-factor", required=True, type=float)
    parser.add_argument("--generator-commit", required=True)
    args = parser.parse_args()

    source = Path(args.source)
    load_dir = Path(args.load_dir)
    load_dir.mkdir(parents=True, exist_ok=True)
    files: dict[str, dict[str, object]] = {}

    for table in TABLES:
        raw = source / f"{table}.tbl"
        cleaned = load_dir / f"{table}.tbl"
        if not raw.exists():
            raise FileNotFoundError(raw)
        with raw.open("rb") as input_handle, cleaned.open("wb") as output_handle:
            for line in input_handle:
                body = line.rstrip(b"\r\n")
                if body.endswith(b"|"):
                    body = body[:-1]
                output_handle.write(body + b"\n")
        rows = row_count(cleaned)
        expected = expected_rows(table, args.scale_factor)
        if expected is not None and rows != expected:
            raise ValueError(f"{table} 行数异常：实际 {rows}，预期 {expected}")
        if table == "lineitem":
            lower = int(5_500_000 * args.scale_factor)
            upper = int(6_500_000 * args.scale_factor)
            if not lower <= rows <= upper:
                raise ValueError(f"lineitem 行数超出合理范围：{rows}")
        files[table] = {
            "rows": rows,
            "bytes": cleaned.stat().st_size,
            "sha256": sha256(cleaned),
            "raw_sha256": sha256(raw),
        }

    manifest = {
        "generator": "electrum/tpch-dbgen",
        "generator_reported_version": "2.14.0",
        "generator_commit": args.generator_commit,
        "scale_factor": args.scale_factor,
        "command": f"dbgen -vf -s {args.scale_factor}",
        "disclaimer": "TPC-H 派生工程数据；未经 TPC 审计，不可与公开 TPC-H 结果比较。",
        "files": files,
    }
    (load_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
