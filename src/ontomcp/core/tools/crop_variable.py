"""Crop Ontology trait-dictionary tools: get_crop_variable, get_crop_trait.

These resolve the Variable <-> Trait/Method/Scale composition that AgroPortal's
CO snapshot cannot serve, via the live cropontology.org BrAPI endpoint
(``core/crop_ontology_client.py``). Cache-first with a 7-day TTL, like the term
tools; the BrAPI records cache in their own ``crop_records`` table.
"""

import logging
from pathlib import Path

from ontomcp.core import cache, config
from ontomcp.core.config import DB_PATH
from ontomcp.core.crop_ontology_client import CropOntologyClient
from ontomcp.core.tools._common import crop_client, is_error, safe_normalize_curie

logger = logging.getLogger("ontomcp")


def _not_crop_ontology(curie: str) -> dict:
    return {
        "error": "not_crop_ontology",
        "detail": (
            "This tool resolves Crop Ontology (CO_*) variables/traits via the "
            "cropontology.org trait dictionary. For other ontologies use get_term."
        ),
        "curie": curie,
    }


async def _get_crop_record(
    curie: str,
    record_type: str,
    fetch,
    db_path: Path,
    client: CropOntologyClient | None,
) -> tuple[dict, bool]:
    """Shared cache-first orchestration for a crop variable/trait lookup."""
    norm, err = safe_normalize_curie(curie)
    if norm is None:
        return err or {}, False
    prefix = norm.split(":", 1)[0]
    if config.ontology_source(prefix) != "agroportal":
        return _not_crop_ontology(norm), False

    cached = cache.get_crop_record_if_fresh(db_path, norm, record_type)
    if cached is not None:
        logger.debug("get_crop_%s cache hit: %s", record_type, norm)
        return cached, True

    logger.info("get_crop_%s cache miss, fetching BrAPI: %s", record_type, norm)
    async with crop_client(client) as cli:
        record = await fetch(cli, norm)
        if is_error(record):
            return record, False
        cache.put_crop_record(db_path, norm, record_type, record.get("label"), record)
        stored = cache.get_crop_record(db_path, norm, record_type)
    return (stored if stored is not None else record), False


async def get_crop_variable(
    curie: str,
    *,
    db_path: Path = DB_PATH,
    client: CropOntologyClient | None = None,
) -> tuple[dict, bool]:
    """Resolve a Crop Ontology Variable into its Trait/Method/Scale triple.

    Returns ``(record, cache_hit)`` where record carries the variable's
    ``trait``/``method``/``scale`` sub-records (each with its own CURIE), plus
    context-of-use, growth stage, scale valid-values, and provenance. Cache-first
    (7-day TTL); propagates not_crop_ontology / not_found / fetch error dicts.
    """
    return await _get_crop_record(
        curie, "variable", lambda cli, c: cli.fetch_variable(c), db_path, client
    )


async def get_crop_trait(
    curie: str,
    *,
    db_path: Path = DB_PATH,
    client: CropOntologyClient | None = None,
) -> tuple[dict, bool]:
    """Resolve a Crop Ontology Trait and list the Variables that measure it.

    Returns ``(record, cache_hit)`` where record carries the trait's name,
    human-readable ``trait_id``, and the CURIEs of its observation ``variables``.
    Cache-first (7-day TTL); propagates not_crop_ontology / not_found / fetch errors.
    """
    return await _get_crop_record(
        curie, "trait", lambda cli, c: cli.fetch_trait(c), db_path, client
    )
