#!/usr/bin/env python3
"""Shared data-loading and entity-resolution helpers for the CRMLS case study."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from pre_processing import classify_brokerage, discover_sold_files, norm_text, subtype_norm


USECOLS = [
    "CloseDate", "ClosePrice", "ListingKey", "ListAgentEmail", "ListAgentFirstName",
    "ListAgentLastName", "ListAgentFullName", "ListOfficeName", "PropertyType",
    "PropertySubType",
]
SFR_SUBTYPES = {"singlefamilyresidence", "singlefamilysfr", "sfr"}
MAJOR_BROKERAGES = [
    "Compass", "Keller Williams", "Coldwell Banker", "RE/MAX",
    "Berkshire Hathaway", "Century 21", "Sotheby's", "eXp", "Redfin", "Others",
]


def clean_email(series: pd.Series) -> pd.Series:
    """Normalize valid email addresses and blank malformed values."""
    normalized = series.fillna("").astype(str).str.lower().str.strip()
    valid = normalized.str.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", na=False)
    return normalized.where(valid, "")


def load_crmls_panels(
    csv_dir: Path,
    chunksize: int = 100_000,
    include_offices: bool = True,
    include_transactions: bool = True,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Stream monthly Sold files and return agent, office, and transaction panels."""
    agent_parts: list[pd.DataFrame] = []
    office_parts: list[pd.DataFrame] = []
    transaction_parts: list[pd.DataFrame] = []
    seen_listing_keys: set[str] = set()

    for _, path in discover_sold_files(csv_dir, None, None):
        print(f"Reading {path.name}")
        try:
            chunks = pd.read_csv(
                path, usecols=lambda column: column in USECOLS, dtype=str,
                chunksize=chunksize, encoding="utf-8", low_memory=False,
            )
        except UnicodeDecodeError:
            chunks = pd.read_csv(
                path, usecols=lambda column: column in USECOLS, dtype=str,
                chunksize=chunksize, encoding="latin1", low_memory=False,
            )

        for data in chunks:
            for column in USECOLS:
                if column not in data:
                    data[column] = ""

            in_scope = (
                norm_text(data["PropertyType"]).eq("residential")
                & subtype_norm(data["PropertySubType"]).isin(SFR_SUBTYPES)
            )
            data = data.loc[in_scope].copy()
            if data.empty:
                continue

            data["close_date"] = pd.to_datetime(data["CloseDate"], errors="coerce")
            data["year"] = data["close_date"].dt.year
            data = data[data["year"].between(2010, 2026)].copy()
            data["price"] = pd.to_numeric(data["ClosePrice"], errors="coerce")
            data["listing_key"] = data["ListingKey"].fillna("").str.strip()

            # Deduplicate nonblank listing keys globally. Blank keys cannot be matched safely.
            duplicate_prior = data["listing_key"].ne("") & data["listing_key"].isin(seen_listing_keys)
            duplicate_chunk = data["listing_key"].ne("") & data["listing_key"].duplicated(keep="first")
            data = data.loc[~(duplicate_prior | duplicate_chunk)].copy()
            seen_listing_keys.update(data.loc[data["listing_key"].ne(""), "listing_key"].tolist())

            name = norm_text(data["ListAgentFullName"])
            fallback_name = norm_text(
                data["ListAgentFirstName"].fillna("") + " " + data["ListAgentLastName"].fillna("")
            )
            name = name.where(name.ne(""), fallback_name)
            email = clean_email(data["ListAgentEmail"])
            data["agent_id"] = np.where(email.ne(""), "email:" + email, "name:" + name)
            data["agent_name"] = name
            data["office_norm"] = norm_text(data["ListOfficeName"])
            data["brokerage"] = classify_brokerage(data["ListOfficeName"])
            data = data[data["agent_name"].ne("") & data["office_norm"].ne("")]
            if data.empty:
                continue

            agent_parts.append(
                data.groupby(
                    ["year", "agent_id", "agent_name", "brokerage", "office_norm"], as_index=False
                ).agg(
                    sides=("listing_key", "size"),
                    volume=("price", "sum"),
                    price_count=("price", "count"),
                )
            )
            if include_offices:
                office_parts.append(
                    data.groupby(["year", "brokerage", "office_norm"], as_index=False).agg(
                        sides=("listing_key", "size"),
                        volume=("price", "sum"),
                        agents=("agent_id", "nunique"),
                    )
                )
            if include_transactions:
                transaction_parts.append(data[["year", "agent_id", "brokerage", "office_norm", "price"]])

    agents = pd.concat(agent_parts, ignore_index=True)
    agents = agents.groupby(
        ["year", "agent_id", "agent_name", "brokerage", "office_norm"], as_index=False
    ).sum(numeric_only=True)

    offices = pd.DataFrame()
    if office_parts:
        offices = pd.concat(office_parts, ignore_index=True)
        offices = offices.groupby(["year", "brokerage", "office_norm"], as_index=False).sum(numeric_only=True)

    transactions = pd.concat(transaction_parts, ignore_index=True) if transaction_parts else pd.DataFrame()
    return agents, offices, transactions


def build_primary_agent_year(agents: pd.DataFrame) -> pd.DataFrame:
    """Choose one primary annual affiliation using sides, volume, then office name."""
    affiliations = agents.sort_values(
        ["year", "agent_id", "sides", "volume", "office_norm"],
        ascending=[True, True, False, False, True],
    )
    primary = affiliations.drop_duplicates(["year", "agent_id"])[
        ["year", "agent_id", "agent_name", "brokerage", "office_norm"]
    ]
    totals = agents.groupby(["year", "agent_id"], as_index=False).agg(
        listing_sides=("sides", "sum"),
        listing_volume=("volume", "sum"),
    )
    return totals.merge(primary, on=["year", "agent_id"], how="left")
