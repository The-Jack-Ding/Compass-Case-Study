#!/usr/bin/env python3
"""Week 3: analyze office growth, acquisitions, and matched agent outcomes."""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from crmls_panel_utils import MAJOR_BROKERAGES, build_primary_agent_year, load_crmls_panels


def analyze_office_growth(offices: pd.DataFrame, output_dir: Path) -> pd.DataFrame:
    annual = offices.groupby(["year", "brokerage"], as_index=False).agg(
        active_offices=("office_norm", "nunique"),
        listing_volume=("volume", "sum"),
        listing_sides=("sides", "sum"),
    )
    annual["volume_per_office"] = annual["listing_volume"] / annual["active_offices"]
    annual["sides_per_office"] = annual["listing_sides"] / annual["active_offices"]
    annual.to_csv(output_dir / "office_growth_annual.csv", index=False)

    charts = [
        ("active_offices", "Active normalized offices", "active_offices.png"),
        ("volume_per_office", "Listing volume per office ($)", "volume_per_office.png"),
        ("sides_per_office", "Listing sides per office", "sides_per_office.png"),
    ]
    for metric, ylabel, filename in charts:
        figure, axis = plt.subplots(figsize=(11, 6))
        for brokerage in MAJOR_BROKERAGES[:-1]:
            series = annual[annual["brokerage"] == brokerage]
            axis.plot(series["year"], series[metric], marker="o", linewidth=1.8, label=brokerage)
        axis.axvline(2025.5, color="#666666", linestyle="--", linewidth=1)
        axis.set(
            title=metric.replace("_", " ").title() + " by Brokerage",
            xlabel="Close year",
            ylabel=ylabel,
        )
        axis.grid(alpha=0.25)
        axis.legend(bbox_to_anchor=(1.02, 1), loc="upper left", fontsize=8)
        figure.tight_layout()
        figure.savefig(output_dir / filename, dpi=200)
        plt.close(figure)
    return annual


def detect_likely_acquisitions(
    panel: pd.DataFrame, offices: pd.DataFrame, output_dir: Path
) -> pd.DataFrame:
    complete = panel[panel["year"] <= 2025].copy()
    events = []
    years = sorted(complete["year"].unique())
    for year in years[:-1]:
        current = offices[(offices["year"] == year) & (offices["brokerage"] != "Compass")]
        following_offices = set(offices.loc[offices["year"] == year + 1, "office_norm"])
        for office in current.itertuples(index=False):
            if office.office_norm in following_offices or office.sides < 10:
                continue
            top_agents = complete[
                (complete["year"] == year) & (complete["office_norm"] == office.office_norm)
            ].nlargest(10, "listing_volume")
            if top_agents.empty:
                continue
            following = complete[
                (complete["year"] == year + 1) & complete["agent_id"].isin(top_agents["agent_id"])
            ]
            moved = following[following["brokerage"] == "Compass"]["agent_id"].nunique()
            migration_rate = moved / len(top_agents)
            if migration_rate >= 0.5:
                events.append(
                    {
                        "disappearance_year": int(year),
                        "source_office": office.office_norm,
                        "source_brokerage_bucket": office.brokerage,
                        "prior_year_sides": int(office.sides),
                        "prior_year_volume": office.volume,
                        "top_agents_tested": len(top_agents),
                        "top_agents_at_compass_next_year": moved,
                        "migration_rate": migration_rate,
                        "classification": "data-inferred likely acquisition; external confirmation required",
                    }
                )
    result = pd.DataFrame(events)
    if not result.empty:
        result = result.sort_values(
            ["disappearance_year", "prior_year_volume"], ascending=[True, False]
        )
    result.to_csv(output_dir / "likely_acquisitions.csv", index=False)
    return result


def analyze_matched_agent_outcomes(
    panel: pd.DataFrame,
    transactions: pd.DataFrame,
    output_dir: Path,
) -> pd.DataFrame:
    complete = panel[panel["year"] <= 2025].copy()
    prior = complete[["agent_id", "year", "brokerage"]].rename(
        columns={"year": "switch_year", "brokerage": "source_brokerage"}
    )
    prior["switch_year"] += 1
    compass_years = complete[
        (complete["year"] <= 2024) & (complete["brokerage"] == "Compass")
    ][["agent_id", "year"]].rename(columns={"year": "switch_year"})
    movers = compass_years.merge(prior, on=["agent_id", "switch_year"])
    movers = movers[movers["source_brokerage"] != "Compass"].drop_duplicates()

    annual_quartiles = transactions[transactions["year"] <= 2025].groupby("year")["price"].quantile(
        [0.25, 0.75]
    ).unstack()
    annual_quartiles.columns = ["q1", "q3"]
    annual_quartiles["lower_fence"] = annual_quartiles["q1"] - 1.5 * (
        annual_quartiles["q3"] - annual_quartiles["q1"]
    )
    annual_quartiles["upper_fence"] = annual_quartiles["q3"] + 1.5 * (
        annual_quartiles["q3"] - annual_quartiles["q1"]
    )
    flagged = transactions.merge(
        annual_quartiles[["lower_fence", "upper_fence"]],
        left_on="year", right_index=True, how="left",
    )
    flagged["price_outlier_iqr"] = (
        flagged["price"].lt(flagged["lower_fence"])
        | flagged["price"].gt(flagged["upper_fence"])
    )
    flagged["luxury"] = flagged["price"].ge(2_000_000)
    flagged.to_csv(
        output_dir / "did_transaction_price_flags.csv.gz", index=False, compression="gzip"
    )
    flagged["price_for_average"] = flagged["price"].where(~flagged["price_outlier_iqr"])
    metrics = flagged.groupby(["agent_id", "year"], as_index=False).agg(
        sides=("price", "size"),
        volume=("price", "sum"),
        avg_sale_price_iqr=("price_for_average", "mean"),
        luxury_share=("luxury", "mean"),
    )

    panel_lookup = complete.set_index(["agent_id", "year"])
    control_pools: dict[tuple[int, str], pd.DataFrame] = {}
    prior_years = complete[complete["year"] <= 2023]
    for (switch_year, source), group in prior_years.groupby([prior_years["year"] + 1, "brokerage"]):
        post = complete[complete["year"] == switch_year + 1][["agent_id", "brokerage"]].rename(
            columns={"brokerage": "post_brokerage"}
        )
        eligible = group.merge(post, on="agent_id")
        eligible = eligible[eligible["post_brokerage"] != "Compass"].sort_values("listing_volume")
        control_pools[(int(switch_year), source)] = eligible

    matches = []
    for mover in movers.itertuples(index=False):
        pre_key = (mover.agent_id, mover.switch_year - 1)
        post_key = (mover.agent_id, mover.switch_year + 1)
        if pre_key not in panel_lookup.index or post_key not in panel_lookup.index:
            continue
        treated_volume = float(panel_lookup.loc[pre_key, "listing_volume"])
        pool = control_pools.get((int(mover.switch_year), mover.source_brokerage), pd.DataFrame())
        pool = pool[pool["agent_id"] != mover.agent_id]
        if pool.empty:
            continue
        values = pool["listing_volume"].to_numpy()
        position = int(np.searchsorted(values, treated_volume))
        choices = [index for index in [position - 1, position] if 0 <= index < len(pool)]
        best = min(
            choices,
            key=lambda index: abs(np.log1p(values[index]) - np.log1p(treated_volume)),
        )
        control = pool.iloc[best]
        matches.append(
            {
                "switch_year": mover.switch_year,
                "source_brokerage": mover.source_brokerage,
                "treated_agent_id": mover.agent_id,
                "control_agent_id": control["agent_id"],
                "treated_pre_volume": treated_volume,
                "control_pre_volume": control["listing_volume"],
                "log_volume_match_distance": abs(
                    np.log1p(control["listing_volume"]) - np.log1p(treated_volume)
                ),
            }
        )
    matched_pairs = pd.DataFrame(matches)
    matched_pairs.to_csv(output_dir / "did_matched_pairs.csv", index=False)

    metric_lookup = metrics.set_index(["agent_id", "year"])
    changes = []
    metric_names = ["volume", "sides", "avg_sale_price_iqr", "luxury_share"]
    for pair in matched_pairs.itertuples(index=False):
        for group, agent_id in [("treated", pair.treated_agent_id), ("control", pair.control_agent_id)]:
            pre_key = (agent_id, pair.switch_year - 1)
            post_key = (agent_id, pair.switch_year + 1)
            if pre_key not in metric_lookup.index or post_key not in metric_lookup.index:
                continue
            changes.append(
                {
                    "switch_year": pair.switch_year,
                    "pair_treated_agent_id": pair.treated_agent_id,
                    "group": group,
                    **{
                        f"change_{metric}": metric_lookup.loc[post_key, metric]
                        - metric_lookup.loc[pre_key, metric]
                        for metric in metric_names
                    },
                }
            )
    pair_changes = pd.DataFrame(changes)
    pair_changes.to_csv(output_dir / "did_pair_changes.csv", index=False)
    summary = pair_changes.groupby("group").agg(
        {column: "mean" for column in pair_changes.columns if column.startswith("change_")}
    ).T
    if {"treated", "control"}.issubset(summary.columns):
        summary["difference_in_differences"] = summary["treated"] - summary["control"]
    summary.reset_index(names="metric").to_csv(output_dir / "did_summary.csv", index=False)
    return summary


def main() -> None:
    project_root = Path(__file__).resolve().parent.parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv-dir", type=Path, default=project_root / "csv")
    parser.add_argument("--output-dir", type=Path, default=project_root / "outputs" / "week3")
    parser.add_argument("--chunksize", type=int, default=100_000)
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    agents, offices, transactions = load_crmls_panels(args.csv_dir, chunksize=args.chunksize)
    panel = build_primary_agent_year(agents)
    analyze_office_growth(offices, args.output_dir)
    detect_likely_acquisitions(panel, offices, args.output_dir)
    analyze_matched_agent_outcomes(panel, transactions, args.output_dir)
    print(f"Week 3 deliverables written to {args.output_dir}")


if __name__ == "__main__":
    main()
