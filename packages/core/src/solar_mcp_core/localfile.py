"""Validate a user-supplied local path for the sync_* loaders.

The local-path branch of a sync tool is agent-reachable, so constrain what can
be staged into the bulk store: an existing *regular* file (not a device,
socket, fifo, or a symlink to one) with a tabular-data extension. No directory
confinement — the documented workflow is "load the dataset file you
downloaded," which lives anywhere under the user's home.
"""

from pathlib import Path

from solar_mcp_core.errors import BadInput

_DATA_SUFFIXES = (".csv", ".tsv", ".csv.gz", ".tsv.gz", ".txt")


def resolve_local_data_file(source: str) -> Path:
    """Return the resolved path of an existing tabular file, or raise BadInput."""
    path = Path(source).expanduser()
    try:
        resolved = path.resolve(strict=True)  # follows symlinks; requires existence
    except (OSError, RuntimeError) as exc:
        raise BadInput(
            field="source",
            value=source,
            allowed=f"an existing file path or https URL ({type(exc).__name__})",
        ) from exc
    if not resolved.is_file():  # rejects directories, devices, sockets, fifos
        raise BadInput(
            field="source",
            value=source,
            allowed="a regular data file (not a directory or special file)",
        )
    if not resolved.name.lower().endswith(_DATA_SUFFIXES):
        raise BadInput(
            field="source",
            value=source,
            allowed=f"a tabular data file ending in one of {_DATA_SUFFIXES}",
        )
    return resolved
