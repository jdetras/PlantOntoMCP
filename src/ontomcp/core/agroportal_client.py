"""Async httpx client for the AgroPortal API (Crop Ontology backend).

AgroPortal is an OntoPortal/BioPortal instance that hosts the Crop Ontology (CO)
per-crop trait dictionaries, which are NOT on EBI OLS4. This client mirrors
``OLSClient``'s public surface (``search``, ``fetch_term``, ``fetch_parents`` /
``fetch_children`` / ``fetch_ancestors`` / ``fetch_descendants``,
``fetch_ontology_version``) and returns the SAME normalized dict shapes, so the
federated client and the tool layer can treat the two backends interchangeably.

Differences from OLS that this module hides:
- **Auth**: AgroPortal requires an API key (header ``Authorization: apikey
  token=<key>``). With no key, every method returns a structured ``no_api_key``
  error instead of hitting the network — the OLS-backed ontologies are unaffected.
- **Identifiers**: classes are addressed by full IRI (e.g.
  ``https://cropontology.org/rdf/CO_320:0000625``); the CURIE is the IRI tail.
  Path segments are SINGLE-URL-encoded (OLS double-encodes).
- **Shapes**: ``prefLabel``/``synonym``/``definition`` (lists), ``obsolete``;
  hierarchy via ``/parents`` `/children` (bare lists) and ``/ancestors``
  `/descendants` (paged ``collection``).

Public methods never raise: on failure they return a structured ``{"error": ...}``
dict (or list of those) so tools never see an unhandled exception.
"""

import asyncio
from urllib.parse import quote

import httpx

from ontomcp.core import config
from ontomcp.core.ols_client import _iri_to_curie, curie_to_iri, normalize_curie


def _class_iri(curie: str) -> str:
    """Build the cropontology.org class IRI for a CO CURIE via ``IRI_TEMPLATES``."""
    return curie_to_iri(curie)


def _encode_iri(iri: str) -> str:
    """Single-URL-encode an IRI for use as an AgroPortal path segment."""
    return quote(iri, safe="")


def _acronym(curie: str) -> str:
    """The AgroPortal ontology acronym for a CURIE — its (uppercase) prefix."""
    return normalize_curie(curie).split(":", 1)[0]


def _parse_definition(obj: dict) -> str | None:
    """First definition string from AgroPortal's ``definition`` list (or None)."""
    defs = obj.get("definition") or []
    if isinstance(defs, list):
        return defs[0] if defs else None
    return defs or None


def _parse_synonyms(obj: dict) -> dict[str, list[str]]:
    """AgroPortal exposes a flat ``synonym`` list — bucket them all as ``exact``."""
    raw = obj.get("synonym") or []
    names = [s for s in raw if isinstance(s, str)] if isinstance(raw, list) else []
    return {"exact": names, "related": [], "narrow": [], "broad": []}


def _parse_class(obj: dict) -> dict:
    """Parse one AgroPortal class object into the dict shape ``cache.put_term`` expects."""
    curie = _iri_to_curie(obj.get("@id", ""))
    if curie is None:
        raise ValueError(f"AgroPortal class has no parseable @id: {obj.get('@id')!r}")
    return {
        "curie": curie,
        "ontology": curie.split(":", 1)[0],
        "label": obj.get("prefLabel"),
        "definition": _parse_definition(obj),
        "is_obsolete": int(bool(obj.get("obsolete", False))),
        "replaced_by": None,
        "consider": [],
        "subsets": [],
        "definition_sources": [],
        # AgroPortal's class display does not carry a reliable leaf flag.
        "has_children": None,
        "is_leaf": None,
        "synonyms": _parse_synonyms(obj),
        "raw_json": obj,
    }


def _parse_hierarchy_node(obj: dict, rel_type: str) -> dict | None:
    """Parse one hierarchy node; return None for unparseable @ids (caller drops)."""
    curie = _iri_to_curie(obj.get("@id", ""))
    if curie is None:
        return None
    return {"curie": curie, "label": obj.get("prefLabel"), "rel_type": rel_type}


class AgroPortalClient:
    """Async AgroPortal client. Use as an async context manager or call ``aclose()``."""

    def __init__(
        self,
        base_url: str = config.AGROPORTAL_BASE_URL,
        api_key: str | None = None,
        timeout: float = config.OLS_TIMEOUT_SECONDS,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        # Resolve the key at construction so a late-set env var (CLI/test) is honored.
        self._api_key = api_key if api_key is not None else config.AGROPORTAL_API_KEY
        self._owns_client = client is None
        headers = {"User-Agent": config.USER_AGENT}
        if self._api_key:
            headers["Authorization"] = f"apikey token={self._api_key}"
        self._client = client or httpx.AsyncClient(
            base_url=base_url,
            timeout=timeout,
            headers=headers,
        )

    async def __aenter__(self) -> "AgroPortalClient":
        return self

    async def __aexit__(self, *exc) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    @property
    def has_key(self) -> bool:
        """True when an API key is configured (network calls are possible)."""
        return bool(self._api_key)

    def _no_key_error(self) -> dict:
        return {
            "error": "no_api_key",
            "detail": (
                "AgroPortal requires an API key for Crop Ontology lookups. Set "
                "AGROPORTAL_API_KEY (free, from https://agroportal.eu/account)."
            ),
        }

    async def _get(self, path: str, params: dict | None = None) -> httpx.Response:
        """GET with retry/backoff on 429 + 5xx and transport/timeout errors.

        Mirrors ``OLSClient._get``: returns the final response (caller inspects
        status); raises ``httpx.HTTPError`` only if every retry hits a network error.
        """
        last_exc: Exception | None = None
        for attempt in range(1, config.OLS_MAX_RETRIES + 1):
            try:
                response = await self._client.get(path, params=params)
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

    async def search(
        self,
        query: str,
        ontologies: list[str] | None = None,
        limit: int = 10,
    ) -> list[dict]:
        """Free-text search. Returns ``[{curie, label, ontology, definition, is_obsolete}]``.

        ``ontologies`` is a list of CO acronyms (e.g. ``["CO_320"]``). AgroPortal's
        own ``ontologies`` filter is loose, so results are also filtered client-side
        to the requested acronyms to guarantee correct scoping.
        """
        if not self.has_key:
            return [self._no_key_error() | {"query": query}]
        # Note: the /search ``display`` (include) param rejects ``obsolete`` (only
        # the class endpoint accepts it); the obsolete flag is returned by default.
        params: dict = {
            "q": query,
            "pagesize": limit,
            "display": "prefLabel,definition,synonym",
        }
        wanted = {o.upper() for o in ontologies} if ontologies else None
        if ontologies:
            params["ontologies"] = ",".join(sorted(wanted))  # type: ignore[arg-type]
        try:
            response = await self._get("/search", params=params)
            response.raise_for_status()
            docs = response.json().get("collection", [])
        except (httpx.HTTPError, ValueError) as exc:
            return [{"error": "search_failed", "detail": str(exc), "query": query}]

        results = []
        for doc in docs:
            curie = _iri_to_curie(doc.get("@id", ""))
            if curie is None:
                continue
            ontology = curie.split(":", 1)[0]
            if wanted is not None and ontology not in wanted:
                continue
            results.append(
                {
                    "curie": curie,
                    "label": doc.get("prefLabel"),
                    "ontology": ontology,
                    "definition": _parse_definition(doc),
                    "is_obsolete": bool(doc.get("obsolete", False)),
                }
            )
            if len(results) >= limit:
                break
        # Report a rank-normalized 0–1 score so it matches the OLS/cache scale.
        total = len(results)
        for i, item in enumerate(results):
            item["score"] = config.rank_score(i, total)
        return results

    async def fetch_term(self, curie: str) -> dict:
        """Fetch a single CO class. Returns the parsed term or an error/not-found dict."""
        if not self.has_key:
            return self._no_key_error() | {"curie": curie}
        normalized = normalize_curie(curie)
        acronym = _acronym(normalized)
        try:
            encoded = _encode_iri(_class_iri(normalized))
        except ValueError as exc:
            return {"error": "bad_curie", "detail": str(exc), "curie": normalized}
        try:
            response = await self._get(
                f"/ontologies/{acronym}/classes/{encoded}",
                params={"display": "prefLabel,definition,synonym,obsolete"},
            )
            if response.status_code == 404:
                return {"error": "not_found", "curie": normalized}
            response.raise_for_status()
            obj = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            return {"error": "fetch_failed", "detail": str(exc), "curie": normalized}
        if not obj or obj.get("errors"):
            return {"error": "not_found", "curie": normalized}
        return _parse_class(obj)

    async def fetch_ontology_version(self, ontology: str) -> str | None:
        """Return the latest submission version/release for a CO ontology, or None.

        Best-effort: any failure (including a missing key) yields None so version
        capture never breaks a lookup.
        """
        if not self.has_key:
            return None
        acronym = ontology.upper()
        try:
            response = await self._get(f"/ontologies/{acronym}/latest_submission")
            response.raise_for_status()
            body = response.json()
        except (httpx.HTTPError, ValueError):
            return None
        version = body.get("version") or body.get("released")
        return version if isinstance(version, str) else None

    async def _fetch_hierarchy(self, curie: str, endpoint: str, rel_type: str) -> list[dict]:
        if not self.has_key:
            return [self._no_key_error() | {"curie": curie}]
        normalized = normalize_curie(curie)
        acronym = _acronym(normalized)
        try:
            encoded = _encode_iri(_class_iri(normalized))
        except ValueError as exc:
            return [{"error": "bad_curie", "detail": str(exc), "curie": normalized}]
        try:
            response = await self._get(f"/ontologies/{acronym}/classes/{encoded}/{endpoint}")
            if response.status_code == 404:
                return []
            response.raise_for_status()
            body = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            return [{"error": "fetch_failed", "detail": str(exc), "curie": normalized}]
        # /parents and /children return a bare list; /ancestors and /descendants
        # return a paged object with a "collection" array.
        nodes = body if isinstance(body, list) else body.get("collection", [])
        parsed = [_parse_hierarchy_node(n, rel_type) for n in nodes]
        return [n for n in parsed if n is not None]

    async def fetch_parents(self, curie: str) -> list[dict]:
        """Fetch DIRECT parent nodes (one hop). Returns ``[{curie, label, rel_type}, ...]``."""
        return await self._fetch_hierarchy(curie, "parents", "is_a")

    async def fetch_children(self, curie: str) -> list[dict]:
        """Fetch DIRECT child nodes (one hop). Returns ``[{curie, label, rel_type}, ...]``."""
        return await self._fetch_hierarchy(curie, "children", "is_a")

    async def fetch_ancestors(self, curie: str) -> list[dict]:
        """Fetch the TRANSITIVE set of ancestor nodes (full closure, flattened)."""
        return await self._fetch_hierarchy(curie, "ancestors", "ancestor")

    async def fetch_descendants(self, curie: str) -> list[dict]:
        """Fetch the TRANSITIVE set of descendant nodes (full closure, flattened)."""
        return await self._fetch_hierarchy(curie, "descendants", "descendant")
