"""Парсер вывода `docker stats --format "{{.Name}},{{.CPUPerc}},{{.MemUsage}}"`
и matplotlib-графики CPU / MEM по контейнерам.

Использование:

    python scripts/plot_docker_stats.py reports/baseline/docker-stats.log \\
        --duration 150 --label "без кэша" \\
        --out reports/baseline/docker-stats.png

    python scripts/plot_docker_stats.py reports/baseline/docker-stats.log \\
                                         reports/cached/docker-stats.log \\
        --duration 150 --label "без кэша" --label "с кэшем" \\
        --out reports/docker-stats-comparison.png
"""
from __future__ import annotations

import argparse
import re
from collections import defaultdict
from pathlib import Path

import matplotlib.pyplot as plt

# Контейнеры shortist (исключаем посторонние, например chatbot-db-1).
TARGET = {"app", "postgres", "redis"}

CTRL = re.compile(r"\x1b\[[\d;]*[A-Za-z]|\x1b\[H|\x1b\[2J|\[[HK]")
MEM_RE = re.compile(r"^([\d.]+)\s*([KMG]i?B)", re.IGNORECASE)


def _to_mib(s: str) -> float:
    m = MEM_RE.match(s.strip())
    if not m:
        return 0.0
    v = float(m.group(1))
    unit = m.group(2).upper()
    if unit.startswith("G"):
        return v * 1024
    if unit.startswith("M"):
        return v
    if unit.startswith("K"):
        return v / 1024
    return v / (1024 * 1024)


def _parse(path: Path) -> dict[str, list[tuple[float, float]]]:
    """Возвращает для каждого контейнера список (cpu_percent, mem_mib)."""
    series: dict[str, list[tuple[float, float]]] = defaultdict(list)
    with path.open(errors="replace") as f:
        for raw in f:
            line = CTRL.sub("", raw).strip()
            if not line or "," not in line:
                continue
            parts = line.split(",", 2)
            if len(parts) != 3:
                continue
            name, cpu, mem = parts
            name = name.strip()
            if name not in TARGET:
                continue
            try:
                cpu_v = float(cpu.strip().rstrip("%"))
            except ValueError:
                continue
            mem_v = _to_mib(mem.split("/")[0])
            series[name].append((cpu_v, mem_v))
    return series


def _plot_single(
    series: dict[str, list[tuple[float, float]]],
    duration: float,
    label: str,
    out: Path,
) -> None:
    fig, (ax_cpu, ax_mem) = plt.subplots(2, 1, figsize=(11, 7), sharex=True)

    for name, samples in series.items():
        if not samples:
            continue
        n = len(samples)
        t = [duration * i / max(n - 1, 1) for i in range(n)]
        cpu = [s[0] for s in samples]
        mem = [s[1] for s in samples]
        ax_cpu.plot(t, cpu, label=name)
        ax_mem.plot(t, mem, label=name)

    ax_cpu.set_ylabel("CPU, %")
    ax_cpu.set_title(f"Нагрузка на контейнеры: {label}")
    ax_cpu.grid(alpha=0.3)
    ax_cpu.legend()

    ax_mem.set_ylabel("Память, MiB")
    ax_mem.set_xlabel("время, с от начала прогона")
    ax_mem.grid(alpha=0.3)
    ax_mem.legend()

    fig.tight_layout()
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=110)
    print(f"сохранил: {out}")


def _plot_compare(
    runs: list[tuple[dict[str, list[tuple[float, float]]], str]],
    duration: float,
    out: Path,
) -> None:
    fig, axes = plt.subplots(len(TARGET), 1, figsize=(11, 9), sharex=True)
    if len(TARGET) == 1:
        axes = [axes]

    for ax, container in zip(axes, sorted(TARGET)):
        for series, label in runs:
            samples = series.get(container, [])
            if not samples:
                continue
            n = len(samples)
            t = [duration * i / max(n - 1, 1) for i in range(n)]
            cpu = [s[0] for s in samples]
            ax.plot(t, cpu, label=label)
        ax.set_title(f"CPU контейнера {container}, %")
        ax.grid(alpha=0.3)
        ax.legend()

    axes[-1].set_xlabel("время, с от начала прогона")
    fig.tight_layout()
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=110)
    print(f"сохранил: {out}")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("inputs", nargs="+")
    p.add_argument("--label", action="append", default=[])
    p.add_argument("--out", required=True, type=Path)
    p.add_argument("--duration", type=float, default=150.0)
    args = p.parse_args()

    if len(args.label) != len(args.inputs):
        raise SystemExit("число --label должно совпадать с числом входных логов")

    runs = [(_parse(Path(p)), label) for p, label in zip(args.inputs, args.label)]

    if len(runs) == 1:
        _plot_single(runs[0][0], args.duration, runs[0][1], args.out)
    else:
        _plot_compare(runs, args.duration, args.out)


if __name__ == "__main__":
    main()
