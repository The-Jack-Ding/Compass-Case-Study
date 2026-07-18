# Compass California Case Study - Week 2 and Week 3 Readout

## Scope and status

This refresh includes CRMLS Sold files from January 2012 through June 2026. The assignment's complete-year analyses end in 2025. Results for 2026 are shown only as YTD context and are explicitly labeled; they are not used as a full-year comparison or as a post-period in the difference-in-differences-style analysis.

Week 2 and Week 3 are complete and reproducible through separate analysis scripts. The final outputs are organized by week, and both pipelines were rerun successfully after the June 2026 file was added. End-to-end QA confirmed one record per agent-year, complete-year comparisons through 2025, 1,622 matched mover/control pairs, and acquisition candidates that satisfy the documented detection thresholds.

## Headline findings

1. **Compass's strongest top-producer gains occurred from 2018 through 2021.** Its share of the top 1% of listing agents rose from 9.3% in 2018 to 20.6% in 2021. The top 1% series moved earlier and remained above the top 5% and top 10% series, consistent with a recruiting strategy tilted toward higher-producing agents.
2. **Coldwell Banker was the largest named source of top-500 moves to Compass.** Across the annual top-500 migration cohorts, 23 observed transitions went from Coldwell Banker to Compass, compared with 8 from Keller Williams and 7 from Sotheby's. The residual "Others" group supplied 32, so additional entity resolution within that bucket remains important.
3. **The acquisition screen strongly detects Pacific Union International.** In 2018, the normalized office disappeared after $1.04B and 618 listing sides, and 9 of its 10 highest-volume agents appeared at Compass in the following year. Compass's own 2018 newsroom announcement confirms its Pacific Union acquisition. The screen also detects Paragon Real Estate Group; contemporaneous reporting confirms that transaction. All other rows remain data-inferred candidates requiring external confirmation.
4. **Compass offices were substantially more productive on this normalization.** Volume per normalized Compass office rose sharply around 2018-2021 and remained above the large legacy franchise buckets. Office counts should be interpreted cautiously because the files expose office display names, not stable office IDs; rebrands and branch naming can split or merge offices.
5. **The matched before/after comparison is directionally positive but not causal.** Across 1,622 matched mover/control pairs, the treated-minus-control change was approximately +$1.69M annual listing volume, +1.36 listing sides, +$39K IQR-filtered average sale price, and +4.57 percentage points in $2M+ luxury concentration. Selection into Compass is non-random, matching is one-to-one on prior volume within source brokerage, and the estimates should be presented as suggestive rather than causal.
6. **June 2026 does not reverse the story, but it is partial.** Compass represented 20.4% of the top 1%, 18.7% of the top 5%, and 17.5% of the top 10% in the January-June 2026 extract. These figures are YTD and should not be compared mechanically with completed calendar years.

## Deliverable map

- Deliverable 2: `agent_year_panel.csv`, `top500_agents_by_year.csv`, `top500_year_over_year_moves.csv`, `migration_matrix_long.csv`, `top5_sources_to_compass.csv`, and `migration_heatmap.png`.
- Deliverable 3: `top_producer_concentration.csv` and `top_producer_concentration.png`.
- Deliverable 4: `office_growth_annual.csv`, `active_offices.png`, `volume_per_office.png`, and `sides_per_office.png`.
- Deliverable 5: `likely_acquisitions.csv`.
- Deliverable 6: `did_transaction_price_flags.csv.gz`, `did_matched_pairs.csv`, `did_pair_changes.csv`, and `did_summary.csv`.

## Methodology

- Scope is `PropertyType = Residential` and normalized `PropertySubType = SingleFamilyResidence`.
- Listing sides are deduplicated globally by nonblank `ListingKey`. Missing listing keys are retained because there is no safe identifier for deduplication.
- Agent identity uses normalized `ListAgentEmail` when it is syntactically valid and normalized full name as a fallback. Primary annual affiliation is the brokerage/office with the most listing sides, with listing volume and normalized office name as tie-breakers.
- The annual top-500 cohort is the union of the top 500 agents by listing volume and top 500 by listing sides. A transition is observed only when the agent is present in the immediately following year.
- Office identity is normalized `ListOfficeName`; no stable office identifier is present in the supplied extract.
- Acquisition candidates require an office with at least 10 prior-year sides to disappear and at least 50% of its ten highest-volume agents (or all agents when fewer than ten) to appear at Compass in the next year.
- Difference-in-differences-style movers are agents whose primary affiliation changes from a non-Compass brokerage to Compass. Each is matched to the nearest prior-volume agent at the same source brokerage who remains non-Compass and is observable in the post year. Metrics compare the year before with the year after the switch; the switch year is omitted. The latest eligible switch year is 2024 because 2025 is the last complete post year.
- Average sale price excludes observations outside the annual Q1/Q3 +/- 1.5 IQR fences. All observations, including the flag, remain in `did_transaction_price_flags.csv.gz`. Luxury concentration is the share of listing sides with `ClosePrice >= $2,000,000`.

## Required caveats before sharing

- Email changes, shared/team emails, common names, and name changes can still merge or split agents. A stable ListAgent MLS identifier would materially improve Deliverables 2, 3, 5, and 6.
- The "Others" taxonomy combines many unrelated brokerages and should not be interpreted as one competitor.
- Disappearance plus agent migration is an acquisition signal, not proof. Cross-reference the high-value candidates with public announcements before labeling them confirmed.
- The matched design controls only for observed prior volume and source brokerage. It does not establish parallel trends or remove selection bias, geography, team structure, tenure, or market-cycle confounding.
- 2026 covers January through June only. Office productivity, volume, sides, and active-agent totals for 2026 are not full-year values.

## Reproduction

Run from the repository root:

```bash
MPLCONFIGDIR=/private/tmp/compass-mpl \
  .venv/bin/python scripts/build_top_agent_migration_and_concentration.py

MPLCONFIGDIR=/private/tmp/compass-mpl \
  .venv/bin/python scripts/analyze_office_growth_acquisitions_and_agent_outcomes.py
```

Both scripts auto-discover files named `CRMLSSoldYYYYMM.csv`, so a newly added monthly file is included on the next run.

## External confirmation sources

- Compass, September 27, 2018: https://www.compass.com/newsroom/press-releases/3IDQv268ZVdjNqCRc93T4t/
- San Francisco Chronicle, July 9, 2018: https://www.sfchronicle.com/business/article/Paragon-Real-Estate-of-SF-acquired-by-Compass-to-13061063.php
