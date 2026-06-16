"""Async httpx client for the Crop Ontology trait dictionary (BrAPI v1).

AgroPortal serves the Crop Ontology (CO) as a static OWL snapshot: it has the
Trait/Method/Scale/Variable term *classes* but not the relationships that link
them, so a Variable's trait-method-scale composition cannot be reconstructed
from it. The live trait dictionary at ``cropontology.org`` exposes that
composition over BrAPI v1:

- ``/brapi/v1/variables/{curie}`` -> a Variable with embedded ``trait`` /
  ``method`` / ``scale`` records (each with its own CURIE);
- ``/brapi/v1/traits/{curie}``    -> a Trait with the list of Variables using it.

This is a separate concern from term lookup (``OLSClient`` / ``AgroPortalClient``),
so it is its own client with its own tools — it does not implement the
``OntologyClient`` protocol. Public methods never raise: on failure they return a
structured ``{"error": ...}`` dict so tools never see an unhandled exception.

No API key is required (the endpoint is public).
"""

import asyncio

import httpx

from ontomcp.core import config


def _curie(db_id) -> str | None:
    """Return a canonical CO CURIE from a BrAPI ``*DbId`` value, or None.

    BrAPI ids are already in CURIE form (e.g. ``CO_320:0000625``); this only
    guards the shape so a missing/odd id is dropped rather than propagated.
    """
    if not isinstance(db_id, str) or ":" not in db_id:
        return None
    return db_id


def _str_list(value) -> list[str]:
    """Coerce a BrAPI value that may be a list, a scalar, or None into a str list."""
    if not value:
        return []
    if isinstance(value, list):
        return [v for v in value if isinstance(v, str)]
    return [value] if isinstance(value, str) else []


def _parse_component(obj, id_key: str) -> dict | None:
    """Parse an embedded trait/method/scale sub-object into a compact dict.

    ``id_key`` is the BrAPI id field (``traitDbId`` / ``methodDbId`` /
    ``scaleDbId``). Returns None when the sub-object or its id is missing.
    """
    if not isinstance(obj, dict):
        return None
    curie = _curie(obj.get(id_key))
    if curie is None:
        return None
    out = {
        "curie": curie,
        "name": obj.get("name"),
        "class": obj.get("class"),
        "description": obj.get("description"),
    }
    # Scale carries its data type and permitted values instead of class/description.
    if id_key == "scaleDbId":
        out["data_type"] = obj.get("dataType")
        valid = obj.get("validValues")
        if isinstance(valid, dict):
            out["valid_values"] = valid
    return out


def _parse_variable(result: dict) -> dict:
    """Parse a BrAPI Variable record into the trait-method-scale triple shape."""
    curie = result.get("observationVariableDbId")
    name = result.get("name")
    return {
        "curie": curie,
        "ontology": curie.split(":", 1)[0] if isinstance(curie, str) and ":" in curie else None,
        "label": name,
        "name": name,
        "synonyms": _str_list(result.get("synonyms")),
        "context_of_use": _str_list(result.get("contextOfUse")),
        "growth_stage": result.get("growthStage"),
        "status": result.get("status"),
        "crop": result.get("crop"),
        "institution": result.get("institution"),
        "scientist": result.get("scientist"),
        "date": result.get("date"),
        "language": result.get("language"),
        "default_value": result.get("defaultValue"),
        "trait": _parse_component(result.get("trait"), "traitDbId"),
        "method": _parse_component(result.get("method"), "methodDbId"),
        "scale": _parse_component(result.get("scale"), "scaleDbId"),
        "raw_json": result,
    }


def _parse_trait(result: dict) -> dict:
    """Parse a BrAPI Trait record, listing the Variables that use it."""
    curie = result.get("traitDbId")
    variables = []
    for var in result.get("observationVariables") or []:
        vid = var.get("observationVariableDbId") if isinstance(var, dict) else var
        vc = _curie(vid)
        if vc and vc not in variables:
            variables.append(vc)
    return {
        "curie": curie,
        "ontology": curie.split(":", 1)[0] if isinstance(curie, str) and ":" in curie else None,
        "label": result.get("name"),
        "name": result.get("name"),
        "trait_id": result.get("traitId"),
        "default_value": result.get("defaultValue"),
        "variables": variables,
        "raw_json": result,
    }


class CropOntologyClient:
    """Async Crop Ontology BrAPI client. Use as an async context manager."""

    def __init__(
        self,
        base_url: str = config.CROPONTOLOGY_BASE_URL,
        timeout: float = config.OLS_TIMEOUT_SECONDS,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(
            base_url=base_url,
            timeout=timeout,
            headers={"User-Agent": config.USER_AGENT},
            follow_redirects=True,
        )

    async def __aenter__(self) -> "CropOntologyClient":
        return self

    async def __aexit__(self, *exc) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def _get(self, path: str) -> httpx.Response:
        """GET with retry/backoff on 429 + 5xx and transport/timeout errors.

        Mirrors ``OLSClient._get``: returns the final response (caller inspects
        status); raises ``httpx.HTTPError`` only if every retry hits a network error.
        """
        last_exc: Exception | None = None
        for attempt in range(1, config.OLS_MAX_RETRIES + 1):
            try:
                response = await self._client.get(path)
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                last_exc = exc
            else:
                if response.status_code not in config.OLS_RETRY_STATUS:
                    return response
                last_exc = None
            if attempt < config.OLS_MAX_RETRIES:
                await asyncio.sleep(config.OLS_BACKOFF_BASE * 2 ** (attempt - 1))
        if last_exc is not None:
            raise last_exc
        return response

    async def _fetch(self, kind: str, curie: str) -> dict:
        """Fetch a BrAPI record (``variables`` or ``traits``) and return its result.

        Returns the bare ``result`` dict, or an error/not-found dict. BrAPI returns
        200 with an empty ``result`` ({}) for an unknown id.
        """
        try:
            response = await self._get(f"/{kind}/{curie}")
            if response.status_code == 404:
                return {"error": "not_found", "curie": curie}
            response.raise_for_status()
            body = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            return {"error": "fetch_failed", "detail": str(exc), "curie": curie}
        result = body.get("result") if isinstance(body, dict) else None
        if not result:
            return {"error": "not_found", "curie": curie}
        return result

    async def fetch_variable(self, curie: str) -> dict:
        """Fetch one Variable with its Trait/Method/Scale composition, or an error dict."""
        result = await self._fetch("variables", curie)
        if "error" in result:
            return result
        return _parse_variable(result)

    async def fetch_trait(self, curie: str) -> dict:
        """Fetch one Trait and the Variables that use it, or an error dict."""
        result = await self._fetch("traits", curie)
        if "error" in result:
            return result
        return _parse_trait(result)
