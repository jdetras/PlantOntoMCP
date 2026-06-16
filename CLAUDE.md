# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

OntoMCP grounds plant and crop concepts to canonical ontology CURIEs (e.g. leaf → `PO:0025034`,
plant height → `TO:0000207`) over the EBI OLS4 API. The registry covers PO, TO, PECO, PPO, PSO,
FLOPO, AGRO, ENVO, PCO (plant/crop) plus GO and SO (crop genomics). The same 14 tools are exposed
three ways: an MCP server (stdio for Claude, SSE for GPT/Codex/remote), a FastAPI HTTP server, and
a Jupyter extension.

## Commands

Tooling is `uv` + `make` (Python 3.11+). `make` targets wrap `uv run`; on Windows call the
`uv run ...` forms directly.

```bash
make install           # uv sync --extra dev --extra jupyter
make test              # unit tests only: pytest -m "not integration"  (MUST pass before any commit)
make test-integration  # integration tests — hits the live EBI OLS4 API, needs network
make lint              # ruff check + ruff format --check
make format            # ruff format (writes)
make types             # mypy src/ontomcp/
make serve-api         # FastAPI on :8000  (uv run ontomcp-api)
make serve-mcp         # MCP server, stdio  (uv run ontomcp-mcp)
ONTOMCP_TRANSPORT=sse make serve-mcp   # MCP over SSE on :8001 for GPT/Codex/remote clients
```

Run a single test:
```bash
uv run pytest tests/test_tools.py::test_get_term_cache_hit -q
uv run pytest -m "not integration" -k synonyms -q
```

There is no separate build step — `hatchling` builds the wheel from `src/ontomcp` on publish.

## Architecture

Three thin entrypoints over one core library. **All business logic lives in `core/`;**
`mcp_server/` and `api/` only adapt transport in and shape output back (a hard project rule).

```
mcp_server/server.py   FastMCP — 14 @mcp.tool() wrappers, each delegating to core.tools
api/                   FastAPI — main.py app factory + routes/ (one router per tool group)
jupyter_ext/           ipywidgets search panel, ipycytoscape graph, %%ontomcp cell magic;
                       talks to the FastAPI server over HTTP via client.py
core/
  config.py            SINGLE source of truth: ONTOLOGIES registry (incl. 42 Crop Ontology
                       entries tagged source="agroportal"), IRI_TEMPLATES, OLS + AgroPortal
                       settings, payload caps, env config. Never redefine these elsewhere.
  ols_client.py        Async httpx client for OLS4 + all CURIE/IRI parsing. Network only —
                       never touches SQLite. Public methods never raise (return error dicts).
  agroportal_client.py Async httpx client for AgroPortal (Crop Ontology backend), same surface
                       as ols_client. Needs AGROPORTAL_API_KEY; keyless calls return no_api_key.
  crop_ontology_client.py  Async httpx client for the cropontology.org BrAPI v1 trait dictionary.
                       Resolves a CO Variable's Trait/Method/Scale triple — links AgroPortal's OWL
                       snapshot lacks. Separate concern: NOT an OntologyClient; public, no API key.
  ontology_client.py   The OntologyClient Protocol that OLS/AgroPortal/Federated satisfy.
  federated_client.py  Routes each lookup to OLS or AgroPortal by config.ontology_source, and
                       partitions/merges search across both. This is the shared client.
  cache.py             SQLite layer (schema, FTS5 search, read/write). The ONLY module that
                       opens a DB connection. Backend-agnostic — caches CO/OLS terms and (in the
                       crop_records table) CO trait-dictionary variables/traits alike.
  tools/               The 14 tool functions — cache-first orchestration lives here.
```

### Request flow (the cache-first pattern)
A tool in `core/tools/` is the orchestrator. Canonical path (see `tools/term.py::get_term`):
1. Normalize the CURIE via `safe_normalize_curie` (returns a structured error dict, never raises).
2. Check the cache: `cache.get_term_if_fresh` (7-day TTL).
3. On a miss, fetch via the shared client (a `FederatedClient`, which routes to OLS or AgroPortal),
   **write back** with `cache.put_term`, then re-read the stored row so the returned shape is
   identical hit-or-miss.

Tool functions return a `(result, cache_hit)` tuple. The MCP/API wrappers unpack and return only
`result`; `cache_hit` exists for tests and instrumentation. **Exception:** `validate_term` never
caches and always hits OLS live — deprecation status must never be served stale.

### Two backends, one interface
CURIEs route to a backend by `config.ontology_source(prefix)`: the 11 EBI OLS4 ontologies →
`OLSClient`, the 42 Crop Ontology (`CO_*`) dictionaries → `AgroPortalClient`. The servers hold a
single `FederatedClient` (implements `OntologyClient`) exactly where they used to hold an
`OLSClient`; tools are unchanged and call it through `_common.ols_client()`. AgroPortal differs
from OLS in three ways the clients hide: it **requires an API key** (`AGROPORTAL_API_KEY` — the one
exception to "no API key required"; keyless CO calls return a `no_api_key` error and OLS is
unaffected), classes are addressed by full IRI single-URL-encoded (OLS double-encodes), and CO
class IRIs carry the CURIE in the tail (`…/rdf/CO_320:0000625`). The cache is backend-agnostic.

### Crop Ontology trait dictionary (third backend)
AgroPortal's CO submission is a static OWL snapshot: it has the Trait/Method/Scale/Variable term
classes but **not the relationships linking them**, so a Variable's trait-method-scale composition
is not reconstructable from it. The live cropontology.org BrAPI v1 endpoint serves that composition.
`crop_ontology_client.CropOntologyClient` (public, no API key) backs two CO-only tools —
`get_crop_variable` (Variable → trait/method/scale triple) and `get_crop_trait` (Trait → its
Variables). These are a *separate concern* from term lookup: the client is not an `OntologyClient`,
the tools route by `config.ontology_source(prefix) == "agroportal"` (else return `not_crop_ontology`)
and get their own shared client via `_common.crop_client()`. Records cache in `crop_records`
(keyed by `(curie, record_type)`, 7-day TTL) holding the full tool-facing dict as JSON.

### Two servers, one cache
Both the MCP and API processes read *and* write the shared SQLite cache through `core/` — neither
touches SQLite directly. Concurrency safety comes from WAL mode + `busy_timeout` (set on every
`cache._connect`), and all writes are idempotent upserts so concurrent writers converge. (Note:
`core/cache.py`'s module docstring still says "FastAPI owns writes; FastMCP reads only" — that is
stale; the rule below is authoritative.)

### Lifespan
Each server initializes the cache schema once and holds a single process-lifetime `FederatedClient`
(MCP: `_lifespan` in `server.py`; API: `lifespan` in `main.py`). `--db-path` is exported to
`ONTOMCP_DB_PATH` at boot so the lifespan resolves it after import-time defaults are set.

---

# OntoMCP — Project Rules

## MCP Tool Design

- Tool docstrings are instructions to the LLM. Write them to describe *when* to call the tool, not what the code does.
- Every tool must have explicit `Args:` documentation — Claude uses these to construct calls.
- Tool names and parameter names must be self-explanatory without reading the docstring.
- Tools must never raise unhandled exceptions — return structured error dicts instead.
- Keep tool output payloads small. Enforce the hard caps defined in `plan.md` (40/50 node limits, 500-term max).

## Architecture Constraints

- No business logic in `mcp_server/` or `api/` — all logic lives in `core/`.
- Cache-first on every OLS call. Never skip SQLite check.
- Never cache `validate_term` results — always hit OLS live.
- Both servers read and write the cache through the shared `core/` (cache-first with write-back on miss); neither server touches SQLite directly. Concurrency safety comes from SQLite WAL mode plus `busy_timeout` (see `config.BUSY_TIMEOUT_MS`), not from restricting writes to one process. All writes must be idempotent (upsert / insert-or-ignore) so concurrent writers converge.
- Every connection must set WAL mode, foreign keys, and the busy timeout on open (`cache._connect`).

## OLS API Etiquette

- Check cache before any outbound request.
- 7-day TTL for term data.
- Retry only on 429 and 5xx — max 3 attempts, exponential backoff.
- Always send `User-Agent: OntoMCP/0.1`.

## CURIE Rules

- Store and return CURIEs with uppercase prefix: `PO:0025034`, never `po:0025034`.
- Strip `obo:` prefix if OLS returns it.
- Use `IRI_TEMPLATES` in `config.py` for all IRI construction — no ad-hoc string building.
- Every registry ontology's CURIE prefix already equals its uppercased registry key, so no prefix
  aliasing is needed; `ols_client._PREFIX_ALIASES` is an empty hook for any future exception.

## Testing

- Unit tests mock the OLS client — never hit the network in unit tests.
- Integration tests are marked `@pytest.mark.integration` and can be skipped offline.
- `pytest -m "not integration"` must always pass clean before any commit.
