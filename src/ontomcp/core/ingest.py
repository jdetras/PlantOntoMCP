"""Bulk-ingest a Crop Ontology's terms into the FTS cache for searchability.

AgroPortal serves every CO class by CURIE but never built a free-text search
index for some submissions (e.g. CO_320 rice, CO_322 maize), so
``search_terms("plant height", ["CO_320"])`` returns nothing even though the term
exists. This module pages the ontology's full class list from AgroPortal and
writes the labels into OntoMCP's own FTS cache, giving us a search index
independent of AgroPortal's gaps. Run once per ontology (it is idempotent):

    uv run ontomcp-ingest-crop CO_320
    uv run ontomcp-ingest-crop --all

After ingestion, CO terms are discoverable via the normal cache-first
``search_terms`` path. This is a batch/offline operation, not a per-request tool.
"""

import asyncio
import logging
import os
from pathlib import Path

from ontomcp.core import cache, config
from ontomcp.core.agroportal_client import AgroPortalClient
from ontomcp.core.logging import configure_logging
from ontomcp.core.tools._common import is_error

logger = logging.getLogger("ontomcp")


async def ingest_crop_ontology(
    acronym: str,
    *,
    db_path: Path = config.DB_PATH,
    client: AgroPortalClient | None = None,
) -> dict:
    """Ingest one CO ontology's classes into the FTS cache.

    Returns ``{"ontology", "ingested"}`` on success, or a structured error dict
    (``not_crop_ontology`` / ``no_api_key`` / ``fetch_failed``). Idempotent.
    """
    acr = acronym.upper()
    if config.ontology_source(acr) != "agroportal":
        return {"error": "not_crop_ontology", "ontology": acronym}

    cache.init_db(db_path)
    owns = client is None
    cli = client or AgroPortalClient()
    try:
        classes = await cli.fetch_all_classes(acr)
    finally:
        if owns:
            await cli.aclose()

    if is_error(classes):
        return classes[0] if isinstance(classes, list) else classes

    count = cache.put_terms(db_path, classes)
    logger.info("ingested %d classes for %s", count, acr)
    return {"ontology": acr, "ingested": count}


async def ingest_all(db_path: Path = config.DB_PATH) -> list[dict]:
    """Ingest every Crop Ontology in the registry, sequentially (one shared client)."""
    results = []
    async with AgroPortalClient() as cli:
        for acr in config.CROP_ONTOLOGIES:
            res = await ingest_crop_ontology(acr, db_path=db_path, client=cli)
            logger.info("%s -> %s", acr, res)
            results.append(res)
    return results


def _resolve_db_path() -> Path:
    raw = os.environ.get("ONTOMCP_DB_PATH")
    return Path(raw).expanduser() if raw else config.DB_PATH


def run() -> None:
    """Entrypoint for the `ontomcp-ingest-crop` script."""
    import argparse

    parser = argparse.ArgumentParser(
        prog="ontomcp-ingest-crop",
        description="Ingest Crop Ontology terms from AgroPortal into the FTS cache.",
    )
    parser.add_argument("acronym", nargs="?", help="CO acronym, e.g. CO_320 (rice)")
    parser.add_argument("--all", action="store_true", help="ingest every CO ontology")
    parser.add_argument("--db-path", default=None, help="SQLite cache file path")
    args = parser.parse_args()

    configure_logging()
    if args.db_path:
        os.environ["ONTOMCP_DB_PATH"] = args.db_path
    db_path = _resolve_db_path()

    if args.all:
        results = asyncio.run(ingest_all(db_path))
        total = sum(r.get("ingested", 0) for r in results)
        logger.info("ingested %d terms across %d ontologies", total, len(results))
        return
    if not args.acronym:
        parser.error("provide a CO acronym (e.g. CO_320) or --all")
    result = asyncio.run(ingest_crop_ontology(args.acronym, db_path=db_path))
    logger.info("%s", result)
