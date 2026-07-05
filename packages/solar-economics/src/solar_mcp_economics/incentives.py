"""Incentive data: the always-available federal table plus DSIRE snapshots.

DSIRE's live API is subscriber-only, so the open path is bulk snapshots:
`sync_incentives` loads a downloaded DSIRE program export (CSV) into the
bulk store and records its vintage; `state_programs` queries it. Every
result cites the snapshot vintage. Without a synced snapshot, tools still
return the federal ITC table (hardcoded current law with citation).
"""

from typing import Any

from pydantic import BaseModel
from solar_mcp_core.bulk import DSIRE_DATASET as DATASET
from solar_mcp_core.bulk import DSIRE_TABLE as TABLE
from solar_mcp_core.bulk import BulkStore, DatasetVintage

from solar_mcp_economics.economics import itc_rate

DSIRE_DOWNLOAD_HELP = (
    "Download a program export from https://programs.dsireusa.org/system/program "
    "(CSV) and pass its path or URL to sync_incentives."
)

# Columns we require of a DSIRE export; extras are kept but unused.
REQUIRED_COLUMNS = ("state", "name", "type", "administrator", "url")


class Incentive(BaseModel):
    name: str
    level: str  # federal | state/local
    type: str
    value: str  # human-readable formula/amount
    administrator: str | None = None
    expiry: str | None = None
    source_url: str


def federal_incentives(install_year: int) -> list[Incentive]:
    rate = itc_rate(install_year)
    schedule = "30% through 2032, 26% in 2033, 22% in 2034, expires 2035"
    return [
        Incentive(
            name="Residential Clean Energy Credit (federal ITC)",
            level="federal",
            type="tax credit",
            value=f"{rate:.0%} of system cost for {install_year} ({schedule})",
            administrator="IRS",
            expiry="2034-12-31",
            source_url="https://www.irs.gov/credits-deductions/residential-clean-energy-credit",
        )
    ]


def sync_snapshot(store: BulkStore, csv_path: Any, vintage: str) -> int:
    """Load a DSIRE export into the bulk store; returns row count.

    Stage-validate-swap: a bad export raises without touching a previously
    synced snapshot or its vintage.
    """
    staging = "sync_staging"
    try:
        count = store.stage_csv(staging, csv_path)
    except Exception as exc:
        store.execute(f'DROP TABLE IF EXISTS "{staging}"')
        raise ValueError(
            f"unreadable CSV ({type(exc).__name__}: {exc}). {DSIRE_DOWNLOAD_HELP}"
        ) from exc
    try:
        columns = {str(row[0]) for row in store.query(f'DESCRIBE "{staging}"')}
        missing = [c for c in REQUIRED_COLUMNS if c not in columns]
        if missing:
            raise ValueError(
                f"DSIRE export is missing expected columns {missing}; got {sorted(columns)}. "
                + DSIRE_DOWNLOAD_HELP
            )
        store.execute(f'CREATE OR REPLACE TABLE {TABLE} AS SELECT * FROM "{staging}"')
        store.set_vintage(DATASET, vintage)
        return count
    finally:
        store.execute(f'DROP TABLE IF EXISTS "{staging}"')


def snapshot_vintage(store: BulkStore) -> DatasetVintage | None:
    return store.vintage(DATASET)


def state_programs(store: BulkStore, state: str) -> list[Incentive]:
    if not store.has_table(TABLE):
        return []
    columns = {str(row[0]) for row in store.query(f"DESCRIBE {TABLE}")}
    has_expiry = "expiry" in columns  # optional column in DSIRE exports
    select = "name, type, administrator, url" + (", expiry" if has_expiry else "")
    rows = store.query(
        f"SELECT {select} FROM {TABLE} WHERE upper(state) = ? ORDER BY name", [state]
    )
    incentives = []
    for row in rows:
        name, kind, admin, url = row[0], row[1], row[2], row[3]
        expiry = row[4] if has_expiry else None
        incentives.append(
            Incentive(
                name=str(name),
                level="state/local",
                type=str(kind),
                value="see program terms",
                administrator=str(admin) if admin is not None else None,
                expiry=str(expiry) if expiry is not None else None,
                source_url=str(url),
            )
        )
    return incentives
