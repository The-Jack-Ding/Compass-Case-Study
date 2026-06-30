#!/usr/bin/env python3

from __future__ import annotations

import argparse
import csv
import re
from collections import defaultdict
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import PercentFormatter
import pandas as pd

EXPECTED_FIELDS = [
    "BuyerAgentAOR",
    "ListAgentAOR",
    "Flooring",
    "ViewYN",
    "WaterfrontYN",
    "BasementYN",
    "PoolPrivateYN",
    "OriginalListPrice",
    "ListingKey",
    "ListAgentEmail",
    "CloseDate",
    "ClosePrice",
    "ListAgentFirstName",
    "ListAgentLastName",
    "Latitude",
    "Longitude",
    "UnparsedAddress",
    "PropertyType",
    "LivingArea",
    "ListPrice",
    "DaysOnMarket",
    "ListOfficeName",
    "BuyerOfficeName",
    "CoListOfficeName",
    "ListAgentFullName",
    "CoListAgentFirstName",
    "CoListAgentLastName",
    "BuyerAgentMlsId",
    "BuyerAgentFirstName",
    "BuyerAgentLastName",
    "BuyerAgentFullName",
    "FireplacesTotal",
    "AssociationFeeFrequency",
    "AboveGradeFinishedArea",
    "ListingKeyNumeric",
    "MLSAreaMajor",
    "TaxAnnualAmount",
    "CountyOrParish",
    "MlsStatus",
    "ElementarySchool",
    "AttachedGarageYN",
    "ParkingTotal",
    "BuilderName",
    "PropertySubType",
    "LotSizeAcres",
    "SubdivisionName",
    "BuyerOfficeAOR",
    "YearBuilt",
    "StreetNumberNumeric",
    "ListingId",
    "BathroomsTotalInteger",
    "City",
    "TaxYear",
    "BuildingAreaTotal",
    "BedroomsTotal",
    "ContractStatusChangeDate",
    "ElementarySchoolDistrict",
    "CoBuyerAgentFirstName",
    "PurchaseContractDate",
    "ListingContractDate",
    "BelowGradeFinishedArea",
    "BusinessType",
    "StateOrProvince",
    "CoveredSpaces",
    "MiddleOrJuniorSchool",
    "FireplaceYN",
    "Stories",
    "HighSchool",
    "Levels",
    "LotSizeDimensions",
    "LotSizeArea",
    "MainLevelBedrooms",
    "NewConstructionYN",
    "GarageSpaces",
    "HighSchoolDistrict",
    "PostalCode",
    "AssociationFee",
    "LotSizeSquareFeet",
    "MiddleOrJuniorSchoolDistrict",
    "OriginatingSystemName",
    "OriginatingSystemSubName",
]

REQUIRED_FIELDS = [
    "CloseDate",
    "ListingContractDate",
    "PurchaseContractDate",
    "ListOfficeName",
    "BuyerOfficeName",
    "ListAgentFullName",
    "BuyerAgentFullName",
    "ClosePrice",
    "ListPrice",
    "OriginalListPrice",
    "CountyOrParish",
    "MLSAreaMajor",
    "PropertyType",
    "PropertySubType",
    "Latitude",
    "Longitude",
    "ListingKey",
]

BROKERAGE_ORDER = [
    "Compass",
    "Keller Williams",
    "Coldwell Banker",
    "RE/MAX",
    "Berkshire Hathaway",
    "Century 21",
    "Sotheby's",
    "eXp",
    "Redfin",
    "Others",
]

DATE_COLUMNS = ["CloseDate", "ListingContractDate", "PurchaseContractDate"]
NUMERIC_COLUMNS = ["ClosePrice", "ListPrice", "OriginalListPrice", "Latitude", "Longitude"]
SFR_SUBTYPE_NORMS = {"singlefamilyresidence", "singlefamilysfr", "sfr"}


# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------

def infer_project_root(script_path: Path) -> Path:
    # Allow the script to run from repo root or scripts/ without path edits.
    script_dir = script_path.resolve().parent
    if (script_dir / "csv").exists() or (script_dir / ".git").exists():
        return script_dir
    if (script_dir.parent / "csv").exists() or (script_dir.parent / ".git").exists():
        return script_dir.parent
    return Path.cwd().resolve()


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)

def discover_sold_files(csv_dir: Path, start_yyyymm: Optional[int], end_yyyymm: Optional[int]) -> List[Tuple[int, Path]]:
    # Find CRMLSSoldYYYYMM.csv files. Prefer normal files over _filled files.
    pattern = re.compile(r"^CRMLSSold(\d{6})(_filled)?\.csv$", re.IGNORECASE)
    grouped: Dict[int, List[Path]] = defaultdict(list)

    for path in csv_dir.glob("CRMLSSold*.csv"):
        if path.name.endswith(".partial"):
            continue
        match = pattern.match(path.name)
        if not match:
            continue
        yyyymm = int(match.group(1))
        if start_yyyymm is not None and yyyymm < start_yyyymm:
            continue
        if end_yyyymm is not None and yyyymm > end_yyyymm:
            continue
        grouped[yyyymm].append(path)

    selected: List[Tuple[int, Path]] = []
    for yyyymm, paths in sorted(grouped.items()):
        def preference(p: Path) -> Tuple[int, int]:
            # 0 = preferred normal non-empty, 1 = filled non-empty, 2 = normal empty, 3 = filled empty
            is_filled = "_filled" in p.stem.lower()
            nonempty = p.stat().st_size > 100
            if not is_filled and nonempty:
                return (0, -p.stat().st_size)
            if is_filled and nonempty:
                return (1, -p.stat().st_size)
            if not is_filled:
                return (2, 0)
            return (3, 0)

        chosen = sorted(paths, key=preference)[0]
        selected.append((yyyymm, chosen))

    return selected


def standardize_schema(df: pd.DataFrame) -> Tuple[pd.DataFrame, List[str], List[str]]:
    # Keep expected fields, fill missing expected fields, and drop extra fields.
    original_cols = list(df.columns)
    missing_cols = [c for c in EXPECTED_FIELDS if c not in original_cols]
    extra_cols = [c for c in original_cols if c not in EXPECTED_FIELDS]

    for col in missing_cols:
        df[col] = ""

    # If BuyerAgentFullName was not present, build it from first/last names.
    if "BuyerAgentFullName" in missing_cols:
        first = df.get("BuyerAgentFirstName", "").fillna("").astype(str)
        last = df.get("BuyerAgentLastName", "").fillna("").astype(str)
        df["BuyerAgentFullName"] = (first + " " + last).str.strip()

    # If ListAgentFullName is missing or blank, build it from first/last names where possible.
    if "ListAgentFullName" in df.columns:
        list_full_blank = is_missing(df["ListAgentFullName"])
        first = df.get("ListAgentFirstName", "").fillna("").astype(str)
        last = df.get("ListAgentLastName", "").fillna("").astype(str)
        fallback = (first + " " + last).str.strip()
        df.loc[list_full_blank & fallback.ne(""), "ListAgentFullName"] = fallback[list_full_blank & fallback.ne("")]

    df = df[EXPECTED_FIELDS]
    return df, extra_cols, missing_cols

def is_missing(series: pd.Series) -> pd.Series:
    text = series.astype("string").str.strip()
    return series.isna() | text.isin(["", "nan", "NaN", "None", "NONE", "null", "NULL", "NaT"])


def norm_text(series: pd.Series) -> pd.Series:
    # Lowercase, trim, remove punctuation-like separators, collapse whitespace.
    text = series.fillna("").astype(str).str.lower().str.strip()
    text = text.str.replace("&", " and ", regex=False)
    text = text.str.replace(r"[^a-z0-9]+", " ", regex=True)
    text = text.str.replace(r"\s+", " ", regex=True).str.strip()
    return text


def subtype_norm(series: pd.Series) -> pd.Series:
    return norm_text(series).str.replace(" ", "", regex=False)


def classify_brokerage(office_name: pd.Series) -> pd.Series:
    # Map raw office names into the fixed brokerage taxonomy for Deliverable 1.
    office_norm = norm_text(office_name)
    brokerage = pd.Series("Others", index=office_name.index, dtype="object")

    # Order matters where names can contain franchise/legal suffixes.
    rules = [
        (r"\bcompass\b", "Compass"),
        (r"\bkeller\s+williams\b|\bkw\b|\bk w\b", "Keller Williams"),
        (r"\bcoldwell\s+banker\b|\bcoldwell\b", "Coldwell Banker"),
        (r"\bre\s*max\b|\bremax\b", "RE/MAX"),
        (r"\bberkshire\s+hathaway\b|\bbhhs\b", "Berkshire Hathaway"),
        (r"\bcentury\s*21\b|\bc21\b", "Century 21"),
        (r"\bsotheby\b|\bsothebys\b", "Sotheby's"),
        (r"\bexp\b|\bexp\s+realty\b", "eXp"),
        (r"\bredfin\b", "Redfin"),
    ]

    for pattern, label in rules:
        mask = office_norm.str.contains(pattern, regex=True, na=False)
        brokerage.loc[mask] = label

    return brokerage


def parse_datetime(series: pd.Series) -> pd.Series:
    return pd.to_datetime(series, errors="coerce", utc=True)


def parse_numeric(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce")


def pct(numerator: float, denominator: float) -> float:
    return float(numerator) / float(denominator) if denominator else 0.0


# -----------------------------------------------------------------------------
# Main processing
# -----------------------------------------------------------------------------

def process_files(
    sold_files: List[Tuple[int, Path]],
    output_dir: Path,
    chunksize: int,
    write_clean_panel: bool,
) -> Dict[str, pd.DataFrame]:
    clean_panel_path = output_dir / "clean_sfr_sold_with_keys.csv"
    if write_clean_panel and clean_panel_path.exists():
        clean_panel_path.unlink()

    monthly_rows = []
    schema_rows = []
    missing_counts: Dict[Tuple[int, str], int] = defaultdict(int)
    monthly_total_rows: Dict[int, int] = defaultdict(int)
    annual_market_parts = []
    office_variant_parts = []
    seen_listing_keys = set()
    first_clean_write = True

    for yyyymm, file_path in sold_files:
        print(f"Processing {file_path.name} ...")
        file_year = yyyymm // 100
        file_month = yyyymm % 100

        month_summary = defaultdict(int)
        month_summary["yyyymm"] = yyyymm
        month_summary["file"] = str(file_path)
        month_summary["file_exists"] = True

        try:
            chunk_iter = pd.read_csv(
                file_path,
                dtype=str,
                chunksize=chunksize,
                encoding="utf-8",
                low_memory=False,
            )
        except UnicodeDecodeError:
            chunk_iter = pd.read_csv(
                file_path,
                dtype=str,
                chunksize=chunksize,
                encoding="latin1",
                low_memory=False,
            )

        for raw_chunk in chunk_iter:
            raw_rows = len(raw_chunk)
            if raw_rows == 0:
                continue

            chunk, extra_cols, missing_cols = standardize_schema(raw_chunk)
            if extra_cols or missing_cols:
                schema_rows.append({
                    "yyyymm": yyyymm,
                    "source_file": str(file_path),
                    "extra_columns_dropped": ";".join(extra_cols),
                    "missing_columns_filled_blank": ";".join(missing_cols),
                    "chunk_rows": raw_rows,
                })

            # Required missingness is calculated after schema standardization.
            for field in REQUIRED_FIELDS:
                missing_counts[(yyyymm, field)] += int(is_missing(chunk[field]).sum())

            # Scope filter: Residential Single Family Residence.
            prop_type_ok = norm_text(chunk["PropertyType"]).eq("residential")
            prop_subtype_ok = subtype_norm(chunk["PropertySubType"]).isin(SFR_SUBTYPE_NORMS)
            scope_mask = prop_type_ok & prop_subtype_ok
            sfr = chunk.loc[scope_mask].copy()

            month_summary["api_or_file_rows_seen"] += raw_rows
            month_summary["filtered_out_non_residential_sfr"] += int((~scope_mask).sum())
            month_summary["rows"] += len(sfr)
            monthly_total_rows[yyyymm] += len(sfr)

            if len(sfr) == 0:
                continue

            # Parse dates and numeric fields.
            for col in DATE_COLUMNS:
                sfr[f"{col}_dt"] = parse_datetime(sfr[col])
            for col in NUMERIC_COLUMNS:
                sfr[f"{col}_num"] = parse_numeric(sfr[col])

            close_dt = sfr["CloseDate_dt"]
            listing_dt = sfr["ListingContractDate_dt"]
            purchase_dt = sfr["PurchaseContractDate_dt"]
            lat = sfr["Latitude_num"]
            lon = sfr["Longitude_num"]

            close_month_ok = (
                close_dt.notna()
                & close_dt.dt.year.eq(file_year)
                & close_dt.dt.month.eq(file_month)
            )

            sfr["close_date_parse_error"] = close_dt.isna()
            sfr["close_date_outside_file_month"] = close_dt.notna() & ~close_month_ok
            sfr["listing_after_close_flag"] = listing_dt.notna() & close_dt.notna() & (listing_dt > close_dt)
            sfr["purchase_after_close_flag"] = purchase_dt.notna() & close_dt.notna() & (purchase_dt > close_dt)
            sfr["listing_after_purchase_flag"] = listing_dt.notna() & purchase_dt.notna() & (listing_dt > purchase_dt)
            sfr["negative_timeline_flag"] = (
                sfr["listing_after_close_flag"]
                | sfr["purchase_after_close_flag"]
                | sfr["listing_after_purchase_flag"]
            )
            sfr["latitude_null_or_zero"] = lat.isna() | lat.eq(0)
            sfr["longitude_null_or_zero"] = lon.isna() | lon.eq(0)
            sfr["positive_longitude"] = lon.gt(0)

            month_summary["close_date_parse_errors"] += int(sfr["close_date_parse_error"].sum())
            month_summary["close_date_outside_month"] += int(sfr["close_date_outside_file_month"].sum())
            month_summary["property_type_not_residential"] += 0
            month_summary["property_subtype_not_sfr"] += 0
            month_summary["listing_after_close_flag"] += int(sfr["listing_after_close_flag"].sum())
            month_summary["purchase_after_close_flag"] += int(sfr["purchase_after_close_flag"].sum())
            month_summary["listing_after_purchase_flag"] += int(sfr["listing_after_purchase_flag"].sum())
            month_summary["negative_timeline_flag"] += int(sfr["negative_timeline_flag"].sum())
            month_summary["latitude_null_or_zero"] += int(sfr["latitude_null_or_zero"].sum())
            month_summary["longitude_null_or_zero"] += int(sfr["longitude_null_or_zero"].sum())
            month_summary["positive_longitude"] += int(sfr["positive_longitude"].sum())

            # Normalized keys required before agent-level migration work.
            sfr["close_year"] = close_dt.dt.year.astype("Int64")
            sfr["list_office_norm"] = norm_text(sfr["ListOfficeName"])
            sfr["buyer_office_norm"] = norm_text(sfr["BuyerOfficeName"])
            sfr["list_agent_norm"] = norm_text(sfr["ListAgentFullName"])
            sfr["buyer_agent_norm"] = norm_text(sfr["BuyerAgentFullName"])
            sfr["list_agent_office_key"] = sfr["list_agent_norm"] + " | " + sfr["list_office_norm"]
            sfr["buyer_agent_office_key"] = sfr["buyer_agent_norm"] + " | " + sfr["buyer_office_norm"]
            sfr["brokerage"] = classify_brokerage(sfr["ListOfficeName"])

            listing_key = sfr["ListingKey"].fillna("").astype(str).str.strip()
            listing_key_missing = listing_key.eq("")
            duplicate_in_chunk = listing_key.duplicated(keep="first") & ~listing_key_missing
            duplicate_global = listing_key.isin(seen_listing_keys) & ~listing_key_missing
            duplicate_listing_key = duplicate_in_chunk | duplicate_global
            sfr["duplicate_listingkey_flag"] = duplicate_listing_key
            month_summary["duplicate_listingkey_rows"] += int(duplicate_listing_key.sum())
            month_summary["duplicate_listingkey_distinct_keys"] += int(listing_key[duplicate_listing_key].nunique())
            month_summary["unique_listing_keys"] += int(listing_key[~listing_key_missing & ~duplicate_listing_key].nunique())
            seen_listing_keys.update(listing_key[~listing_key_missing & ~duplicate_listing_key].tolist())

            # Market-share aggregation uses valid CloseDate year and excludes duplicate listing keys.
            analysis = sfr.loc[
                close_dt.notna() & sfr["close_year"].notna() & ~sfr["duplicate_listingkey_flag"]
            ].copy()
            if len(analysis):
                grouped = (
                    analysis.groupby(["close_year", "brokerage"], dropna=False)
                    .agg(
                        listing_sides=("ListingKey", "count"),
                        listing_volume=("ClosePrice_num", "sum"),
                        close_price_missing=("ClosePrice_num", lambda x: int(x.isna().sum())),
                    )
                    .reset_index()
                )
                annual_market_parts.append(grouped)

                variants = (
                    analysis.groupby(["close_year", "brokerage", "ListOfficeName"], dropna=False)
                    .agg(
                        listing_sides=("ListingKey", "count"),
                        listing_volume=("ClosePrice_num", "sum"),
                    )
                    .reset_index()
                )
                office_variant_parts.append(variants)

            if write_clean_panel:
                output_cols = EXPECTED_FIELDS + [
                    "close_year",
                    "ClosePrice_num",
                    "ListPrice_num",
                    "OriginalListPrice_num",
                    "Latitude_num",
                    "Longitude_num",
                    "list_office_norm",
                    "buyer_office_norm",
                    "list_agent_norm",
                    "buyer_agent_norm",
                    "list_agent_office_key",
                    "buyer_agent_office_key",
                    "brokerage",
                    "close_date_parse_error",
                    "close_date_outside_file_month",
                    "listing_after_close_flag",
                    "purchase_after_close_flag",
                    "listing_after_purchase_flag",
                    "negative_timeline_flag",
                    "latitude_null_or_zero",
                    "longitude_null_or_zero",
                    "positive_longitude",
                    "duplicate_listingkey_flag",
                ]
                sfr[output_cols].to_csv(
                    clean_panel_path,
                    mode="w" if first_clean_write else "a",
                    header=first_clean_write,
                    index=False,
                    quoting=csv.QUOTE_MINIMAL,
                )
                first_clean_write = False

        monthly_rows.append(dict(month_summary))

    monthly_summary = pd.DataFrame(monthly_rows).fillna(0)
    if not monthly_summary.empty:
        int_cols = [c for c in monthly_summary.columns if c not in ["file", "file_exists"]]
        for c in int_cols:
            monthly_summary[c] = pd.to_numeric(monthly_summary[c], errors="coerce").fillna(0)

    missing_rows = []
    for (yyyymm, field), miss_count in sorted(missing_counts.items()):
        total = monthly_total_rows.get(yyyymm, 0)
        missing_rows.append({
            "yyyymm": yyyymm,
            "field": field,
            "missing_count": miss_count,
            "rows": total,
            "missing_pct": pct(miss_count, total),
            "over_90_pct_missing": pct(miss_count, total) > 0.90,
        })
    missing_by_month = pd.DataFrame(missing_rows)

    if not missing_by_month.empty:
        total_rows_all = int(missing_by_month.drop_duplicates("yyyymm")["rows"].sum())
        missing_overall = (
            missing_by_month.groupby("field")
            .agg(
                total_missing=("missing_count", "sum"),
                max_month_missing_pct=("missing_pct", "max"),
                avg_month_missing_pct=("missing_pct", "mean"),
                months_over_90_pct_missing=("over_90_pct_missing", "sum"),
            )
            .reset_index()
        )
        missing_overall["overall_missing_pct"] = missing_overall["total_missing"] / total_rows_all
        missing_overall = missing_overall.sort_values("overall_missing_pct", ascending=False)
    else:
        missing_overall = pd.DataFrame()

    if annual_market_parts:
        annual_market = pd.concat(annual_market_parts, ignore_index=True)
        annual_market = (
            annual_market.groupby(["close_year", "brokerage"], dropna=False)
            .agg(
                listing_sides=("listing_sides", "sum"),
                listing_volume=("listing_volume", "sum"),
                close_price_missing=("close_price_missing", "sum"),
            )
            .reset_index()
        )
        annual_market["close_year"] = annual_market["close_year"].astype(int)

        # Fill missing brokerage-year combinations with zeros for cleaner charts.
        years = sorted(annual_market["close_year"].dropna().unique().tolist())
        full_index = pd.MultiIndex.from_product([years, BROKERAGE_ORDER], names=["close_year", "brokerage"])
        annual_market = (
            annual_market.set_index(["close_year", "brokerage"])
            .reindex(full_index, fill_value=0)
            .reset_index()
        )

        totals = annual_market.groupby("close_year").agg(
            total_listing_sides=("listing_sides", "sum"),
            total_listing_volume=("listing_volume", "sum"),
        ).reset_index()
        annual_market = annual_market.merge(totals, on="close_year", how="left")
        annual_market["market_share_sides"] = annual_market["listing_sides"] / annual_market["total_listing_sides"]
        annual_market["market_share_volume"] = annual_market["listing_volume"] / annual_market["total_listing_volume"]
        annual_market["brokerage"] = pd.Categorical(annual_market["brokerage"], categories=BROKERAGE_ORDER, ordered=True)
        annual_market = annual_market.sort_values(["close_year", "brokerage"])
    else:
        annual_market = pd.DataFrame()

    if office_variant_parts:
        variants = pd.concat(office_variant_parts, ignore_index=True)
        variant_summary = (
            variants.groupby(["brokerage", "ListOfficeName"], dropna=False)
            .agg(
                first_year=("close_year", "min"),
                last_year=("close_year", "max"),
                active_year_count=("close_year", "nunique"),
                listing_sides=("listing_sides", "sum"),
                listing_volume=("listing_volume", "sum"),
            )
            .reset_index()
            .sort_values(["brokerage", "listing_volume"], ascending=[True, False])
        )
        # Top 50 raw office names per taxonomy bucket for manual spelling/rebrand QA.
        variant_summary = variant_summary.groupby("brokerage", group_keys=False).head(50)
    else:
        variant_summary = pd.DataFrame()

    schema_log = pd.DataFrame(schema_rows)

    return {
        "monthly_summary": monthly_summary,
        "missing_by_month": missing_by_month,
        "missing_overall": missing_overall,
        "annual_market": annual_market,
        "office_variants": variant_summary,
        "schema_log": schema_log,
    }


# -----------------------------------------------------------------------------
# Outputs
# -----------------------------------------------------------------------------

def write_chart(annual_market: pd.DataFrame, output_path: Path, share_col: str, title: str, ylabel: str) -> None:
    if annual_market.empty:
        return

    pivot = annual_market.pivot(index="close_year", columns="brokerage", values=share_col)
    pivot = pivot[[c for c in BROKERAGE_ORDER if c in pivot.columns]]

    fig, ax = plt.subplots(figsize=(13, 7))
    pivot.plot(ax=ax, marker="o", linewidth=2)
    ax.set_title(title)
    ax.set_xlabel("Close year")
    ax.set_ylabel(ylabel)
    ax.yaxis.set_major_formatter(PercentFormatter(1.0))
    ax.grid(True, alpha=0.3)
    ax.legend(title="Brokerage", bbox_to_anchor=(1.02, 1), loc="upper left")
    fig.tight_layout()
    fig.savefig(output_path, dpi=200)
    plt.close(fig)


def compute_compass_crossings(annual_market: pd.DataFrame) -> pd.DataFrame:
    if annual_market.empty:
        return pd.DataFrame()

    pivot = annual_market.pivot(index="close_year", columns="brokerage", values="market_share_volume").sort_index()
    rows = []
    for competitor in [b for b in BROKERAGE_ORDER if b not in ["Compass", "Others"]]:
        if competitor not in pivot.columns or "Compass" not in pivot.columns:
            continue
        mask = pivot["Compass"].fillna(0) > pivot[competitor].fillna(0)
        if mask.any():
            first_year = int(mask[mask].index.min())
            rows.append({
                "competitor": competitor,
                "first_year_compass_market_share_volume_exceeded_competitor": first_year,
                "compass_share_that_year": pivot.loc[first_year, "Compass"],
                "competitor_share_that_year": pivot.loc[first_year, competitor],
            })
        else:
            rows.append({
                "competitor": competitor,
                "first_year_compass_market_share_volume_exceeded_competitor": "not crossed",
                "compass_share_that_year": None,
                "competitor_share_that_year": None,
            })
    return pd.DataFrame(rows)


def write_outputs(output_dir: Path, sold_files: List[Tuple[int, Path]], data: Dict[str, pd.DataFrame], write_clean_panel: bool) -> None:
    ensure_dir(output_dir)

    data["monthly_summary"].to_csv(output_dir / "qa_monthly_summary_week1.csv", index=False)
    data["missing_by_month"].to_csv(output_dir / "qa_required_field_missing_by_month.csv", index=False)
    data["missing_overall"].to_csv(output_dir / "qa_required_field_missing_overall.csv", index=False)
    data["office_variants"].to_csv(output_dir / "qa_top_office_name_variants.csv", index=False)
    data["schema_log"].to_csv(output_dir / "qa_schema_standardization_week1.csv", index=False)
    data["annual_market"].to_csv(output_dir / "brokerage_market_share_annual.csv", index=False)

    crossings = compute_compass_crossings(data["annual_market"])
    crossings.to_csv(output_dir / "compass_crossings.csv", index=False)

    write_chart(
        data["annual_market"],
        output_dir / "brokerage_market_share_by_volume.png",
        "market_share_volume",
        "California Residential SFR Listing-Volume Market Share",
        "Share of listing volume",
    )
    write_chart(
        data["annual_market"],
        output_dir / "brokerage_market_share_by_sides.png",
        "market_share_sides",
        "California Residential SFR Listing-Side Market Share",
        "Share of listing sides",
    )


# -----------------------------------------------------------------------------
# CLI
# -----------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    script_path = Path(__file__).resolve()

    if script_path.parent.name == "scripts":
        project_root = script_path.parent.parent
    else:
        project_root = script_path.parent

    parser = argparse.ArgumentParser(description="Create Week 1 QA outputs and Deliverable 1 market-share draft.")
    parser.add_argument("--csv-dir", type=Path, default=project_root / "csv", help="Folder containing CRMLSSoldYYYYMM.csv files.")
    parser.add_argument("--output-dir", type=Path, default=project_root / "outputs" / "week1", help="Folder for Week 1 outputs.")
    parser.add_argument("--start-yyyymm", type=int, default=None, help="Optional first month to include, like 201501.")
    parser.add_argument("--end-yyyymm", type=int, default=None, help="Optional last month to include, like 202512.")
    parser.add_argument("--chunksize", type=int, default=100_000, help="Rows per pandas chunk.")
    parser.add_argument("--write-clean-panel", action="store_true", help="Write the large clean_sfr_sold_with_keys.csv file.")

    return parser.parse_args()

def main() -> None:
    args = parse_args()
    csv_dir = args.csv_dir.resolve()
    output_dir = args.output_dir.resolve()
    ensure_dir(output_dir)

    if not csv_dir.exists():
        raise SystemExit(f"CSV folder not found: {csv_dir}")

    sold_files = discover_sold_files(csv_dir, args.start_yyyymm, args.end_yyyymm)
    if not sold_files:
        raise SystemExit(f"No CRMLSSoldYYYYMM.csv files found in {csv_dir}")

    print(f"Discovered {len(sold_files)} monthly sold files.")
    print(f"First file: {sold_files[0][0]} -> {sold_files[0][1].name}")
    print(f"Last file:  {sold_files[-1][0]} -> {sold_files[-1][1].name}")
    print(f"Output directory: {output_dir}")

    data = process_files(
        sold_files=sold_files,
        output_dir=output_dir,
        chunksize=args.chunksize,
        write_clean_panel=args.write_clean_panel
    )
    write_outputs(output_dir, sold_files, data, write_clean_panel=args.write_clean_panel)

    print("\nDone. Week 1 outputs written to:")
    print(output_dir)
    print("\nStart with:")
    print(output_dir / "brokerage_market_share_by_volume.png")


if __name__ == "__main__":
    main()
