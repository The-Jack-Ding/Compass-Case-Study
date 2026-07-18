# Compass California Case Study

This repository analyzes California CRMLS Sold transactions to evaluate whether Compass's growth was primarily associated with recruiting top-producing agents, acquiring brokerages, or expanding organically.

The current data covers January 2012 through June 2026. The formal year-over-year analyses use complete calendar years through 2025. Results for 2026 are included only as year-to-date context and are labeled accordingly.

## Current findings

- Compass's share of the top 1% of California listing agents increased from 9.3% in 2018 to 20.6% in 2021. The top 1% series rose earlier and stayed above the top 5% and top 10% series, supporting a recruiting strategy focused on high producers.
- Coldwell Banker was the largest identifiable source of top-500 agents moving to Compass. A large residual source group remains in `Others`, so that bucket should not be interpreted as a single competitor.
- The acquisition screen detected Pacific Union International and Paragon Real Estate Group. Both events were independently confirmed through public sources. Other candidates remain data-inferred until independently verified.
- Pacific Union produced the strongest acquisition signal: the normalized office disappeared after approximately $1.04 billion in observed listing volume and 618 listing sides in 2018, while 9 of its 10 highest-volume agents appeared at Compass in the next year.
- The Week 3 matched analysis contains 1,622 mover/control pairs. Relative to matched agents who remained outside Compass, Compass movers experienced an average change of approximately $1.69 million in annual listing volume, 1.36 listing sides, $39,000 in IQR-filtered average sale price, and 4.57 percentage points in $2 million-plus luxury concentration.
- The matched results are suggestive, not causal. Agents select into brokerages, and the available data does not fully control for geography, team structure, tenure, or local market conditions.

## Repository structure

```text
Compass-Case-Study/
├── csv/                         Confidential monthly CRMLS Sold extracts
├── outputs/
│   ├── week1/                   Ingestion QA and market-share draft
│   ├── week2/                   Agent migration and producer concentration
│   ├── week3/                   Office, acquisition, and matched-outcome analysis
│   └── reports/                 Written analytical readouts
├── qa/                          Historical extraction QA logs
└── scripts/
    ├── pre_processing.py
    ├── crmls_panel_utils.py
    ├── build_top_agent_migration_and_concentration.py
    └── analyze_office_growth_acquisitions_and_agent_outcomes.py
```

The raw data, QA exports, and generated outputs are intentionally ignored by Git because they contain confidential MLS information or reproducible derived data.

## Setup

Create or activate a Python environment containing:

- pandas
- numpy
- matplotlib

The existing local environment can be used from the repository root:

```bash
.venv/bin/python --version
```

Place monthly files in `csv/` using the naming convention:

```text
CRMLSSoldYYYYMM.csv
```

Both analysis scripts discover matching files automatically. Adding a new monthly file therefore requires no code changes.

## Week 1: ingestion, QA, and market share

Run:

```bash
.venv/bin/python scripts/pre_processing.py
```

Week 1 validates the source files, standardizes the expected schema, filters to Residential Single Family Residence, creates date and coordinate QA flags, deduplicates listing keys, normalizes brokerage names, and produces the initial annual market-share analysis.

Default output: `outputs/week1/`

## Week 2: top-agent migration and concentration

Run:

```bash
MPLCONFIGDIR=/private/tmp/compass-mpl \
  .venv/bin/python scripts/build_top_agent_migration_and_concentration.py
```

This script:

1. Builds a primary agent-year affiliation panel.
2. Ranks agents annually by listing volume and listing sides.
3. Defines the top-500 cohort as the union of both rankings.
4. Tracks observed year-over-year brokerage transitions.
5. Produces migration matrices and the top source brokerages feeding Compass.
6. Measures Compass's share of the top 1%, 5%, and 10% of listing agents.

Default output: `outputs/week2/`

Key files:

- `agent_year_panel.csv`
- `top500_agents_by_year.csv`
- `top500_year_over_year_moves.csv`
- `migration_matrix_long.csv`
- `top5_sources_to_compass.csv`
- `migration_heatmap.png`
- `top_producer_concentration.csv`
- `top_producer_concentration.png`

## Week 3: office growth, acquisitions, and agent outcomes

Run:

```bash
MPLCONFIGDIR=/private/tmp/compass-mpl \
  .venv/bin/python scripts/analyze_office_growth_acquisitions_and_agent_outcomes.py
```

This script:

1. Measures active offices, listing volume per office, and listing sides per office.
2. Flags disappearing offices whose leading agents migrate to Compass.
3. Identifies agents whose primary affiliation changes to Compass.
4. Matches each mover to a similar prior-volume agent at the same source brokerage.
5. Compares changes from the year before to the year after the move.
6. Retains an IQR outlier flag for sale prices and separately calculates luxury concentration.

Default output: `outputs/week3/`

Key files:

- `office_growth_annual.csv`
- `active_offices.png`
- `volume_per_office.png`
- `sides_per_office.png`
- `likely_acquisitions.csv`
- `did_transaction_price_flags.csv.gz`
- `did_matched_pairs.csv`
- `did_pair_changes.csv`
- `did_summary.csv`

## Shared methodology

- **Scope:** `PropertyType = Residential` and normalized `PropertySubType = SingleFamilyResidence`.
- **Transaction deduplication:** nonblank `ListingKey` values are deduplicated across all monthly files. Blank keys are retained because no safe matching identifier exists.
- **Agent identity:** normalized `ListAgentEmail` is used when valid; normalized full name is the fallback.
- **Primary annual affiliation:** the office/brokerage with the most listing sides, followed by listing volume and normalized office name as deterministic tie-breakers.
- **Office identity:** normalized `ListOfficeName`, because a stable office identifier is not consistently available in the supplied extract.
- **Acquisition screen:** an office must have at least 10 prior-year sides, disappear in the next year, and have at least 50% of its ten highest-volume agents appear at Compass.
- **Matched outcome design:** movers are compared with the closest prior-volume agent from the same source brokerage who remains outside Compass and is observed in the post year. The switch year itself is omitted.
- **Price treatment:** annual IQR fences flag outlying sale prices. Flags are retained in the full transaction output; outliers are excluded only from the average-sale-price metric.
- **Luxury threshold:** closing price of at least $2 million.
- **Partial 2026:** January through June 2026 is YTD context and is excluded from complete-year transitions and matched pre/post windows.

## Important limitations

- Email changes, shared emails, common names, and name changes can split or merge agent histories.
- Office display-name changes can split one physical office or combine distinct branches.
- The `Others` brokerage bucket contains many unrelated firms.
- Disappearance followed by migration is an acquisition signal, not independent proof of an acquisition.
- The matched analysis does not establish random assignment, parallel pre-trends, or causality.
