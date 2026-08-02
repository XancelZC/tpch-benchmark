#!/usr/bin/env python3
"""从指定 run 的原始记录和汇总结果生成图表。"""

from __future__ import annotations

import argparse
import csv
from collections import defaultdict
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.font_manager as fm
import matplotlib.pyplot as plt


def configure_font() -> None:
    """选择 macOS 中文字体，找不到时使用 matplotlib 默认字体。"""
    for font_path in (
        "/System/Library/Fonts/PingFang.ttc",
        "/System/Library/Fonts/STHeiti Light.ttc",
        "/System/Library/Fonts/Hiragino Sans GB.ttc",
    ):
        path = Path(font_path)
        if path.exists():
            fm.fontManager.addfont(path)
            plt.rcParams["font.family"] = fm.FontProperties(fname=font_path).get_name()
            break
    plt.rcParams["axes.unicode_minus"] = False


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("run_dir", type=Path)
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()
    run_dir = args.run_dir
    output = args.output or (run_dir / "charts")
    output.mkdir(parents=True, exist_ok=True)
    configure_font()

    raw = read_csv(run_dir / "raw_records.csv")
    summary = read_csv(run_dir / "comparison_summary.csv")
    base_database = raw[0]["database"]
    databases = list(dict.fromkeys(row["database"] for row in raw))
    total_seconds: dict[str, float] = defaultdict(float)
    query_times: dict[tuple[str, str], list[float]] = defaultdict(list)
    for row in raw:
        if row["success"] == "True":
            elapsed = float(row["elapsed_ms"])
            total_seconds[row["database"]] += elapsed / 1000
            query_times[(row["database"], row["query_id"])].append(elapsed)

    overall = [row for row in summary if row["record_type"] == "overall"]
    comparison = {row["other_database"]: row for row in overall}

    fig, ax = plt.subplots(figsize=(10, 6))
    labels = databases
    values = [total_seconds[name] for name in labels]
    colors = ["#2ecc71", "#3498db", "#f39c12", "#e74c3c"][: len(labels)]
    bars = ax.bar(labels, values, color=colors)
    ax.set_ylabel("总耗时（秒）")
    ax.set_title("最终 run 四库总耗时对比（5 轮正式测试）")
    ax.set_yscale("log")
    for bar, value in zip(bars, values):
        ax.text(bar.get_x() + bar.get_width() / 2, value * 1.08, f"{value:.1f}s", ha="center")
    ax.grid(axis="y", alpha=0.3)
    fig.tight_layout()
    fig.savefig(output / "overall_total.png", dpi=150)
    plt.close(fig)

    labels = [f"YMatrix vs\n{name}" for name in databases[1:]]
    values = [float(comparison[name]["geomean_speedup"]) for name in databases[1:]]
    fig, ax = plt.subplots(figsize=(10, 6))
    bars = ax.bar(labels, values, color=["#3498db", "#f39c12", "#e74c3c"][: len(values)])
    ax.axhline(1, color="black", linestyle="--", linewidth=1)
    ax.set_ylabel("几何均值 speedup（x）")
    ax.set_title("YMatrix 对各库的几何均值 speedup")
    for bar, value in zip(bars, values):
        ax.text(bar.get_x() + bar.get_width() / 2, value * 1.05, f"{value:.2f}x", ha="center")
    ax.grid(axis="y", alpha=0.3)
    fig.tight_layout()
    fig.savefig(output / "speedup_summary.png", dpi=150)
    plt.close(fig)

    query_ids = sorted(
        {row["query_id"] for row in raw},
        key=lambda value: int(value[1:]),
    )
    other = databases[1]
    base_values = [sum(query_times[(base_database, q)]) / len(query_times[(base_database, q)]) for q in query_ids]
    other_values = [sum(query_times[(other, q)]) / len(query_times[(other, q)]) for q in query_ids]
    fig, ax = plt.subplots(figsize=(14, 6))
    x = list(range(len(query_ids)))
    width = 0.38
    ax.bar([i - width / 2 for i in x], base_values, width, label=base_database, color="#2ecc71")
    ax.bar([i + width / 2 for i in x], other_values, width, label=other, color="#3498db")
    ax.set_xticks(x)
    ax.set_xticklabels([q.upper() for q in query_ids], rotation=45)
    ax.set_ylabel("平均耗时（毫秒）")
    ax.set_title(f"逐查询耗时对比：{base_database} vs {other}")
    ax.legend()
    ax.grid(axis="y", alpha=0.3)
    fig.tight_layout()
    fig.savefig(output / "query_compare.png", dpi=150)
    plt.close(fig)

    print(f"图表已生成：{output}")


if __name__ == "__main__":
    main()
