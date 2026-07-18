#!/usr/bin/env python3
"""Week 2: build top-agent rankings, migration matrices, and concentration trends."""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from crmls_panel_utils import MAJOR_BROKERAGES, build_primary_agent_year, load_crmls_panels


def build_migration_deliverables(panel: pd.DataFrame, output_dir: Path) -> None:
    complete = panel[panel["year"] <= 2025].copy()
    complete["rank_volume"] = complete.groupby("year")["listing_volume"].rank(method="first", ascending=False)
    complete["rank_sides"] = complete.groupby("year")["listing_sides"].rank(method="first", ascending=False)
    complete["top500"] = (complete["rank_volume"] <= 500) | (complete["rank_sides"] <= 500)
    complete.to_csv(output_dir / "agent_year_panel.csv", index=False)
    complete[complete["top500"]].to_csv(output_dir / "top500_agents_by_year.csv", index=False)

    cohort = complete[complete["top500"]].copy()
    next_year = complete[["year", "agent_id", "brokerage"]].rename(
        columns={"year": "next_year", "brokerage": "to_brokerage"}
    )
    moves = cohort.merge(next_year, on="agent_id", how="inner")
    moves = moves[moves["next_year"].eq(moves["year"] + 1)].rename(
        columns={"brokerage": "from_brokerage"}
    )
    moves.to_csv(output_dir / "top500_year_over_year_moves.csv", index=False)

    matrix = (
        moves.groupby(["year", "from_brokerage", "to_brokerage"])
        .size().rename("agents").reset_index()
    )
    matrix.to_csv(output_dir / "migration_matrix_long.csv", index=False)

    sources = (
        moves[(moves["to_brokerage"] == "Compass") & (moves["from_brokerage"] != "Compass")]
        .groupby(["year", "from_brokerage"]).size().rename("agents_to_compass").reset_index()
    )
    sources["source_rank"] = sources.groupby("year")["agents_to_compass"].rank(
        method="first", ascending=False
    )
    sources[sources["source_rank"] <= 5].sort_values(["year", "source_rank"]).to_csv(
        output_dir / "top5_sources_to_compass.csv", index=False
    )

    heatmap = (
        moves.groupby(["from_brokerage", "to_brokerage"]).size().unstack(fill_value=0)
        .reindex(index=MAJOR_BROKERAGES, columns=MAJOR_BROKERAGES, fill_value=0)
    )
    figure, axis = plt.subplots(figsize=(11, 8))
    image = axis.imshow(heatmap.values, cmap="Blues", aspect="auto")
    axis.set_xticks(range(len(heatmap.columns)), heatmap.columns, rotation=45, ha="right")
    axis.set_yticks(range(len(heatmap.index)), heatmap.index)
    for row in range(len(heatmap.index)):
        for column in range(len(heatmap.columns)):
            value = int(heatmap.iloc[row, column])
            axis.text(
                column, row, f"{value:,}", ha="center", va="center", fontsize=7,
                color="white" if value > heatmap.values.max() * 0.55 else "black",
            )
    figure.colorbar(image, ax=axis, label="Agent transitions")
    axis.set_title("Top-500 Agent Brokerage Transitions, 2012-2025")
    axis.set_xlabel("Brokerage in following year")
    axis.set_ylabel("Brokerage in cohort year")
    figure.tight_layout()
    figure.savefig(output_dir / "migration_heatmap.png", dpi=200)
    plt.close(figure)


def build_concentration_deliverables(panel: pd.DataFrame, output_dir: Path) -> None:
    rows = []
    for year, annual in panel.groupby("year"):
        annual = annual.sort_values("listing_volume", ascending=False).reset_index(drop=True)
        active_agents = len(annual)
        for proportion, label in [(0.01, "Top 1%"), (0.05, "Top 5%"), (0.10, "Top 10%")]:
            band_size = max(1, int(np.ceil(active_agents * proportion)))
            band = annual.head(band_size)
            rows.append(
                {
                    "year": int(year),
                    "band": label,
                    "agents_in_band": band_size,
                    "compass_agents": int((band["brokerage"] == "Compass").sum()),
                    "compass_share": float((band["brokerage"] == "Compass").mean()),
                }
            )

    concentration = pd.DataFrame(rows)
    concentration.to_csv(output_dir / "top_producer_concentration.csv", index=False)

    figure, axis = plt.subplots(figsize=(11, 6))
    for label in ["Top 1%", "Top 5%", "Top 10%"]:
        band = concentration[concentration["band"] == label]
        axis.plot(band["year"], 100 * band["compass_share"], marker="o", label=label)
    axis.axvline(2025.5, color="#666666", linestyle="--", linewidth=1)
    axis.text(2025.55, axis.get_ylim()[1] * 0.9, "2026 YTD", fontsize=9)
    axis.set(
        title="Compass Share of California's Highest-Volume Listing Agents",
        xlabel="Close year",
        ylabel="Compass share (%)",
    )
    axis.grid(alpha=0.25)
    axis.legend()
    figure.tight_layout()
    figure.savefig(output_dir / "top_producer_concentration.png", dpi=200)
    plt.close(figure)


def main() -> None:
    project_root = Path(__file__).resolve().parent.parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv-dir", type=Path, default=project_root / "csv")
    parser.add_argument("--output-dir", type=Path, default=project_root / "outputs" / "week2")
    parser.add_argument("--chunksize", type=int, default=100_000)
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    agents, _, _ = load_crmls_panels(
        args.csv_dir, chunksize=args.chunksize,
        include_offices=False, include_transactions=False,
    )
    panel = build_primary_agent_year(agents)
    build_migration_deliverables(panel, args.output_dir)
    build_concentration_deliverables(panel, args.output_dir)
    print(f"Week 2 deliverables written to {args.output_dir}")


if __name__ == "__main__":
    main()
