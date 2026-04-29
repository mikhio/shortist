"""Постобработка stats_history.csv от Locust → matplotlib-графики.

Использование:

    # один прогон (PR #1)
    python scripts/plot_loadtest.py reports/baseline/run_stats_history.csv \\
                                    --label "без кэша" \\
                                    --out reports/baseline/latency-vs-users.png

    # сравнение двух прогонов (PR #2)
    python scripts/plot_loadtest.py reports/baseline/run_stats_history.csv \\
                                    reports/cached/run_stats_history.csv \\
                                    --label "без кэша" --label "с кэшем" \\
                                    --out reports/comparison.png

Источник: https://matplotlib.org
"""
from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from pathlib import Path

import matplotlib.pyplot as plt


@dataclass
class Sample:
    timestamp: float
    user_count: int
    rps: float
    p50: float
    p95: float
    failures_per_s: float


def _load(path: Path) -> list[Sample]:
    samples: list[Sample] = []
    with path.open() as f:
        reader = csv.DictReader(f)
        for row in reader:
            # Берём только агрегированные строки (Name == "Aggregated")
            if row.get("Name") != "Aggregated":
                continue
            try:
                samples.append(
                    Sample(
                        timestamp=float(row["Timestamp"]),
                        user_count=int(row["User Count"]),
                        rps=float(row["Requests/s"]),
                        p50=float(row["50%"]) if row["50%"] != "N/A" else 0.0,
                        p95=float(row["95%"]) if row["95%"] != "N/A" else 0.0,
                        failures_per_s=float(row["Failures/s"]),
                    )
                )
            except (KeyError, ValueError):
                continue
    return samples


def _plot_single(samples: list[Sample], label: str, out: Path) -> None:
    if not samples:
        raise SystemExit(f"нет данных в файле для метки {label!r}")

    t0 = samples[0].timestamp
    t = [s.timestamp - t0 for s in samples]
    users = [s.user_count for s in samples]
    rps = [s.rps for s in samples]
    p95 = [s.p95 for s in samples]

    fig, ax1 = plt.subplots(figsize=(11, 5))

    ax1.set_xlabel("время, с от начала прогона")
    ax1.set_ylabel("p95 latency, мс", color="tab:red")
    ax1.plot(t, p95, color="tab:red", label="p95 latency")
    ax1.tick_params(axis="y", labelcolor="tab:red")

    ax2 = ax1.twinx()
    ax2.set_ylabel("RPS / users", color="tab:blue")
    ax2.plot(t, rps, color="tab:blue", label="RPS")
    ax2.plot(t, users, color="tab:gray", linestyle="--", label="users (ступени)")
    ax2.tick_params(axis="y", labelcolor="tab:blue")

    fig.suptitle(f"Нагрузочный профиль: {label}")
    fig.tight_layout()

    lines1, labels1 = ax1.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax1.legend(lines1 + lines2, labels1 + labels2, loc="upper left")

    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=110)
    print(f"сохранил: {out}")


def _plot_comparison(
    runs: list[tuple[list[Sample], str]], out: Path
) -> None:
    fig, (ax_lat, ax_rps) = plt.subplots(2, 1, figsize=(11, 7), sharex=True)

    for samples, label in runs:
        if not samples:
            continue
        t0 = samples[0].timestamp
        t = [s.timestamp - t0 for s in samples]
        ax_lat.plot(t, [s.p95 for s in samples], label=label)
        ax_rps.plot(t, [s.rps for s in samples], label=label)

    ax_lat.set_ylabel("p95 latency, мс")
    ax_lat.set_title("Сравнение прогонов: p95 latency")
    ax_lat.legend()
    ax_lat.grid(alpha=0.3)

    ax_rps.set_ylabel("RPS")
    ax_rps.set_xlabel("время, с от начала прогона")
    ax_rps.set_title("RPS")
    ax_rps.legend()
    ax_rps.grid(alpha=0.3)

    fig.tight_layout()
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=110)
    print(f"сохранил: {out}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("inputs", nargs="+", help="один или несколько CSV-файлов")
    parser.add_argument(
        "--label",
        action="append",
        default=[],
        help="метка для каждого CSV (повторять по числу файлов)",
    )
    parser.add_argument("--out", required=True, type=Path, help="путь до PNG")
    args = parser.parse_args()

    if len(args.label) != len(args.inputs):
        raise SystemExit("число --label должно совпадать с числом CSV-файлов")

    runs = [(_load(Path(p)), label) for p, label in zip(args.inputs, args.label)]

    if len(runs) == 1:
        _plot_single(runs[0][0], runs[0][1], args.out)
    else:
        _plot_comparison(runs, args.out)


if __name__ == "__main__":
    main()
