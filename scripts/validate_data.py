#!/usr/bin/env python3
"""校验数据文件基数、关系完整性和标准查询谓词命中情况。"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

TABLE_FIELDS = {
    "region": 3,
    "nation": 4,
    "supplier": 7,
    "customer": 8,
    "part": 9,
    "partsupp": 5,
    "orders": 9,
    "lineitem": 16,
}


def rows(path: Path):
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            values = line.rstrip("\n").split("|")
            yield line_number, values


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("data_dir", nargs="?", default="data/load")
    args = parser.parse_args()
    data_dir = Path(args.data_dir)
    manifest = json.loads((data_dir / "manifest.json").read_text(encoding="utf-8"))

    for table, field_count in TABLE_FIELDS.items():
        path = data_dir / f"{table}.tbl"
        actual_rows = 0
        for line_number, values in rows(path):
            actual_rows += 1
            if len(values) != field_count:
                raise ValueError(
                    f"{table}:{line_number} 字段数 {len(values)}，预期 {field_count}"
                )
        expected_rows = manifest["files"][table]["rows"]
        if actual_rows != expected_rows:
            raise ValueError(f"{table} 行数 {actual_rows}，清单记录 {expected_rows}")

    order_keys = {int(values[0]) for _, values in rows(data_dir / "orders.tbl")}
    part_keys = {int(values[0]) for _, values in rows(data_dir / "part.tbl")}
    supplier_keys = {int(values[0]) for _, values in rows(data_dir / "supplier.tbl")}
    partsupp_pairs: set[tuple[int, int]] = set()
    for line_number, values in rows(data_dir / "partsupp.tbl"):
        pair = (int(values[0]), int(values[1]))
        if pair in partsupp_pairs:
            raise ValueError(f"partsupp:{line_number} 出现重复键 {pair}")
        partsupp_pairs.add(pair)

    missing_orders = missing_parts = missing_suppliers = missing_pairs = 0
    commit_before_receipt = 0
    for _, values in rows(data_dir / "lineitem.tbl"):
        order_key, part_key, supplier_key = map(int, values[:3])
        missing_orders += order_key not in order_keys
        missing_parts += part_key not in part_keys
        missing_suppliers += supplier_key not in supplier_keys
        missing_pairs += (part_key, supplier_key) not in partsupp_pairs
        commit_before_receipt += values[11] < values[12]
    if any((missing_orders, missing_parts, missing_suppliers, missing_pairs)):
        raise ValueError(
            "lineitem 关系完整性失败："
            f"order={missing_orders}, part={missing_parts}, "
            f"supplier={missing_suppliers}, partsupp={missing_pairs}"
        )
    if commit_before_receipt == 0:
        raise ValueError("lineitem 日期分布异常：没有 commitdate < receiptdate 的记录")

    part_predicates = {"green": 0, "forest": 0, "economy_anodized_steel": 0}
    for _, values in rows(data_dir / "part.tbl"):
        name = values[1].lower()
        part_type = values[4].lower()
        part_predicates["green"] += "green" in name
        part_predicates["forest"] += name.startswith("forest")
        part_predicates["economy_anodized_steel"] += part_type == "economy anodized steel"
    if any(value == 0 for value in part_predicates.values()):
        raise ValueError(f"标准查询谓词未命中：{part_predicates}")

    print(
        json.dumps(
            {
                "status": "ok",
                "scale_factor": manifest["scale_factor"],
                "row_counts": {
                    table: manifest["files"][table]["rows"] for table in TABLE_FIELDS
                },
                "predicate_hits": part_predicates,
                "commit_before_receipt": commit_before_receipt,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
