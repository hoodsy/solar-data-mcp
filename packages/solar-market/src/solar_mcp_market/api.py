"""Typed calls to the USPVDB (PostgREST) and AHJ Registry endpoints."""

from dataclasses import dataclass
from typing import Any

from solar_mcp_core.http import FetchedResponse, SolarHttpClient

from solar_mcp_market.models import Bbox, UspvdbProject

USPVDB_PATH = "/api/uspvdb/v1/projects"
AHJ_PATH = "/api/v1/ahj/"


@dataclass
class UspvdbResult:
    projects: list[UspvdbProject]
    fetched: FetchedResponse


@dataclass
class AhjResult:
    results: list[dict[str, Any]]
    fetched: FetchedResponse


async def uspvdb_projects(
    client: SolarHttpClient,
    *,
    state: str | None = None,
    bbox: Bbox | None = None,
    min_capacity_mw: float | None = None,
    limit: int = 25,
) -> UspvdbResult:
    # PostgREST filter syntax: column=op.value, and=(...) for conjunctions.
    params: dict[str, Any] = {"order": "p_cap_ac.desc.nullslast", "limit": limit}
    if state is not None:
        params["p_state"] = f"eq.{state}"
    if bbox is not None:
        params["and"] = (
            f"(xlong.gte.{bbox.west},xlong.lte.{bbox.east},"
            f"ylat.gte.{bbox.south},ylat.lte.{bbox.north})"
        )
    if min_capacity_mw is not None:
        params["p_cap_ac"] = f"gte.{min_capacity_mw}"
    fetched = await client.get_json(USPVDB_PATH, params)
    projects = [UspvdbProject.model_validate(item) for item in fetched.data]
    return UspvdbResult(projects, fetched)


async def ahj_lookup(client: SolarHttpClient, *, lat: float, lon: float) -> AhjResult:
    fetched = await client.get_json(AHJ_PATH, {"latitude": lat, "longitude": lon})
    body = fetched.data if isinstance(fetched.data, dict) else {}
    results = body.get("results", [])
    return AhjResult(results if isinstance(results, list) else [], fetched)
