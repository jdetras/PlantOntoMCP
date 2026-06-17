"""search_terms tool: FTS-first, OLS fallback, write results back to cache.

Crop Ontology terms are served from our own FTS index: AgroPortal does not
search-index some CO submissions, so before the FTS read we lazily ingest any CO
ontology that is in scope but not freshly ingested. This makes CO terms
discoverable (and is what keeps a CO ontology from being silently excluded by the
cache-first short-circuit when only OLS rows are cached for a query).
"""

import logging
from pathlib import Path

from ontomcp.core import cache, config
from ontomcp.core.agroportal_client import AgroPortalClient
from ontomcp.core.config import CROP_INGEST_TTL_DAYS, DB_PATH, SEARCH_LIMIT_MAX
from ontomcp.core.ontology_client import OntologyClient
from ontomcp.core.tools._common import is_error, normalize_ontologies, ols_client

logger = logging.getLogger("ontomcp")


async def _ensure_crop_ingested(
    onts: list[str] | None,
    db_path: Path,
    ingest_client: AgroPortalClient | None,
) -> None:
    """Lazily ingest any in-scope Crop Ontology not freshly indexed in FTS.

    Only runs for CO ontologies explicitly named in ``ontologies`` (an unscoped
    search does not trigger a mass ingest of all 42). Best-effort: an ingest
    failure is logged and search proceeds with whatever is already cached.
    """
    if not onts:
        return
    # Imported lazily: ingest imports the tools package, so a top-level import here
    # would create a tools <-> ingest cycle (and break the ingest CLI entrypoint).
    from ontomcp.core.ingest import ingest_crop_ontology

    for ont in onts:
        if config.ontology_source(ont) != "agroportal":
            continue
        if cache.is_crop_ingested_fresh(db_path, ont, CROP_INGEST_TTL_DAYS):
            continue
        logger.info("search_terms lazily ingesting Crop Ontology %s", ont)
        result = await ingest_crop_ontology(ont, db_path=db_path, client=ingest_client)
        if is_error(result):
            logger.warning("lazy ingest of %s failed: %s", ont, result)


async def search_terms(
    query: str,
    ontologies: list[str] | None = None,
    limit: int = 10,
    *,
    db_path: Path = DB_PATH,
    client: OntologyClient | None = None,
    ingest_client: AgroPortalClient | None = None,
) -> tuple[list[dict], bool]:
    """Search ontology terms by free text. Cache (FTS5) first, OLS on a miss.

    Returns ``(results, cache_hit)`` where results is
    ``[{curie, label, ontology, definition, score}, ...]`` and ``cache_hit`` is
    True when served from the FTS cache. On an OLS failure, returns the client's
    structured error list with ``cache_hit=False``. ``limit`` is clamped to
    ``[1, SEARCH_LIMIT_MAX]`` to keep payloads small.

    Any Crop Ontology in ``ontologies`` is lazily ingested into the FTS index
    before the read (once per ``CROP_INGEST_TTL_DAYS``), so CO terms AgroPortal
    never search-indexed are still found. ``ingest_client`` is an injection seam
    for that ingest (tests); production creates an AgroPortalClient on demand.
    """
    onts = normalize_ontologies(ontologies)
    limit = max(1, min(limit, SEARCH_LIMIT_MAX))

    await _ensure_crop_ingested(onts, db_path, ingest_client)

    hits = cache.fts_search(db_path, query, onts, limit)
    if hits:
        logger.debug("search_terms cache hit: %r (%d results)", query, len(hits))
        return hits, True

    logger.info("search_terms cache miss, fetching OLS: %r", query)
    async with ols_client(client) as cli:
        results = await cli.search(query, onts, limit)
    if is_error(results):
        return results, False

    for term in results:
        if not term.get("curie") or not term.get("label"):
            continue
        # Persist enough for future FTS hits; full record fills in via get_term.
        cache.put_term(
            db_path,
            {
                "curie": term["curie"],
                "ontology": term["ontology"],
                "label": term["label"],
                "definition": term.get("definition"),
            },
        )
    return results, False
