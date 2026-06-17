# Changelog

All notable changes to OntoMCP are documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
OntoMCP uses [Semantic Versioning](https://semver.org/).

---

## [Unreleased]

### Added
- **Lazy auto-ingest of Crop Ontology terms in `search_terms`.** A search scoped to a CO
  ontology (e.g. `search_terms("plant height", ["CO_320"])`) now ingests that ontology's
  terms into the FTS index on first use (once per 30 days, tracked in a `crop_ingests`
  table), so CO terms are discoverable with no manual step. The manual
  `ontomcp-ingest-crop` / `make ingest-crop` still exists for bulk/offline population.
  This also resolves the earlier finding that the FTS cache-first short-circuit could
  silently exclude Crop Ontology results: CO is now guaranteed in the index before the read.
- **Crop Ontology term ingestion (`ontomcp-ingest-crop`, `make ingest-crop`).** AgroPortal
  serves every CO class by CURIE but never built a free-text search index for some submissions
  (rice `CO_320`, maize `CO_322`, …), so `search_terms("plant height", ["CO_320"])` returned
  nothing even though the term exists. The new batch loader pages an ontology's full class list
  from AgroPortal into OntoMCP's FTS cache (~14s for rice's 1,422 classes), making CO terms
  discoverable via the normal `search_terms` path independent of AgroPortal's indexing gaps.
  Idempotent; run per-ontology or `--all`. New `core/ingest.py`, `cache.put_terms` bulk upsert,
  `AgroPortalClient.fetch_all_classes`.
- **Crop Ontology trait dictionary (`get_crop_variable`, `get_crop_trait`).** Two new
  tools resolve a Crop Ontology Variable into its Trait/Method/Scale triple (and a Trait
  into the Variables that measure it) via the live cropontology.org BrAPI v1 endpoint.
  AgroPortal's CO snapshot carries the term classes but not the links between them; this
  fills that gap with precise CURIEs for phenotyping annotation. New
  `core/crop_ontology_client.py` (public BrAPI client, no API key), `core/tools/crop_variable.py`,
  `/crop/variable/{curie}` and `/crop/trait/{curie}` HTTP routes, and a `crop_records`
  cache table (7-day TTL). CO-only — other ontologies return `not_crop_ontology`.
- Auto-load a local `.env` at startup (via `python-dotenv`) so `AGROPORTAL_API_KEY` and
  other settings are picked up without exporting them or duplicating into a host config.
- **Crop Ontology (CO) via AgroPortal.** 42 per-crop trait dictionaries (Rice `CO_320`,
  Wheat `CO_321`, Maize `CO_322`, …) are now a second backend behind the shared tools.
  A new `FederatedClient` routes each CURIE to its source (EBI OLS4 or AgroPortal) and
  merges `search` results across both. AgroPortal requires a free API key
  (`AGROPORTAL_API_KEY`); when unset, the OLS4 ontologies work normally and CO lookups
  return a structured `no_api_key` message. New `core/agroportal_client.py`,
  `core/federated_client.py`, and `core/ontology_client.py` (shared `OntologyClient`
  protocol); `suggest_ontology` routes recognized crops to their CO dictionary.
  Known limit: CO trait/method/scale category nodes use name-based IRIs without CURIEs, so
  CO `get_parents`/`get_children` can be sparse; the other tools are unaffected.

### Changed
- **Retargeted the ontology registry from biomedical to plant & crop domains.** The
  registry now serves the Plant Ontology (PO), Plant Trait Ontology (TO), PECO, PPO,
  PSO, FLOPO, AGRO, ENVO, and PCO via the EBI OLS4 API, with GO and SO retained for
  crop genomics. The previous biomedical set (MONDO, HPO, ChEBI, UBERON, CL, EFO,
  MeSH, NCIT, DOID, PR) has been removed. All 12 tools, both servers, the cache, and
  the Jupyter extension are unchanged — only the ontology sources differ.
- `suggest_ontology` keyword rules and example terms retuned for plant/crop research
  contexts (anatomy, traits, growth stages, stress, agronomy, environment, genomics).
- Dropped the `HP` → `HPO` CURIE prefix alias; no plant/crop ontology needs aliasing
  (`_PREFIX_ALIASES` is now an empty extension hook).

### Added
- `get_parents` / `get_children` tools and `/term/{curie}/parents` `…/children` routes:
  true one-hop `is_a` edges, the new source of truth for the relationships table and
  `get_term_graph`
- Obsolete-term `consider` alternates surfaced in `get_term` and `validate_term`
- `warnings` on `get_term` for obsolete terms and `do_not_annotate`-subset terms
- `is_obsolete` flag on every `search_terms` result
- `mapping_predicate` on `map_across_ontologies` results (`skos:exactMatch` vs
  `heuristic_label`), and curated `annotation.database_cross_reference` xrefs
- Provenance on `get_term`: `definition_sources`, `subsets`, `has_children`/`is_leaf`,
  and `ontology_version` (also reported in `/health`)
- Three pharma/oncology ontologies: NCIT, DOID, PR
- Dual MCP transport: stdio (default, Claude) and SSE (`ONTOMCP_TRANSPORT=sse`)
  for GPT, Codex CLI, and remote clients — the server is now client-agnostic
- `.env.example` documenting all environment variables
- README "Connecting clients" section covering both transports
- MIT License
- CONTRIBUTING.md with development setup and PR checklist
- GitHub CI workflow: pytest, ruff, mypy on every pull request
- GitHub PR template and issue templates (bug report, feature request)
- Makefile with `install`, `test`, `lint`, `types`, `serve-api`, `serve-mcp` targets
- `pyproject.toml`: author metadata, project URLs, ruff and mypy configuration

### Changed
- `get_ancestors` / `get_descendants` now correctly report the **transitive** closure
  (`depth="transitive"`) and no longer record transitive pairs as direct edges; use
  `get_parents` / `get_children` for one-hop relations. Hierarchy nodes carry honest
  `rel_type` (`is_a` for direct, `ancestor`/`descendant` for transitive) instead of a
  blanket `is_a`
- `map_across_ontologies` heuristic label matches are capped below curated xrefs and are
  reported as candidates, not asserted equivalences
- Cache schema gained `consider`, `subsets`, `definition_sources`, `has_children`,
  `is_leaf` columns and an `ontology_versions` table; existing cache files upgrade in
  place (additive migration)

### Fixed
- Graph topology corruption: edges no longer fabricate a direct link between a term and a
  distant transitive ancestor
- `make types` / CI mypy ran against a non-existent `ontomcp/` path (exited 0
  without checking); now points at `src/ontomcp/` and the codebase is mypy-clean
- Resolved 9 latent type errors surfaced by the corrected mypy path

---

## [0.1.0] - Unreleased

Initial release.

### Added
- SQLite cache layer with FTS5 full-text search and WAL mode (`core/cache.py`)
- Async OLS4 API client with retry logic (`core/ols_client.py`)
- 10 core tool functions: `search_terms`, `get_term`, `find_synonyms`, `validate_term`,
  `suggest_ontology`, `get_ancestors`, `get_descendants`, `map_across_ontologies`,
  `bulk_annotate`, `get_term_graph`
- FastAPI HTTP server with OpenAPI docs at `/docs`
- FastMCP server exposing all 10 tools to any MCP client (stdio + SSE)
- Jupyter extension: search panel, interactive term graph, `%%ontomcp` cell magic
- Support for 8 ontologies: GO, MONDO, HPO, ChEBI, UBERON, CL, EFO, MeSH
