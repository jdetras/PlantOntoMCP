# PlantOntoMCP

**Ontology grounding for plant and crop scientists.**

PlantOntoMCP is a client-agnostic MCP server and Jupyter extension for notebooks. It resolves
plant and crop concepts to canonical ontology terms — leaf becomes `PO:0025034`, plant
height becomes `TO:0000207` — with no hallucinated IDs and no API key required for the core
ontologies. It works with any MCP-compatible client: Claude (Desktop / Code), GPT, Codex CLI,
Cursor, and others.

> A plant/crop adaptation of [OntoMCP](https://github.com/jeanlouishoneine-tech/OntoMCP) by
> Jean-Louis Honeine, which targets biomedical ontologies. See [Acknowledgements](#acknowledgements).

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/)

---

## What it does

- **14 tools** — search, fetch, validate, map, annotate, and graph ontology terms
  (including direct `get_parents` / `get_children` alongside transitive `get_ancestors` / `get_descendants`)
- **11 OLS4 ontologies** — PO, TO, PECO, PPO, PSO, FLOPO, AGRO, ENVO, PCO (plant/crop),
  plus GO and SO (crop genomics) via the EBI OLS4 API
- **42 Crop Ontology dictionaries** — Rice (CO_320), Wheat (CO_321), Maize (CO_322), Cassava,
  Banana, Common Bean, … served via AgroPortal (optional — needs a free API key)
- **Crop Ontology trait dictionary** — `get_crop_variable` / `get_crop_trait` resolve a CO
  Variable's Trait–Method–Scale triple (the precise CURIEs for phenotyping annotation) from
  the live cropontology.org BrAPI endpoint — no API key needed
- **SQLite cache** — fast offline lookups, 7-day TTL, FTS5 full-text search
- **Client-agnostic MCP** — all 14 tools work in Claude (stdio) and GPT / Codex CLI / Cursor (SSE)
- **Jupyter extension** — search panel, interactive term graph, `%%ontomcp` cell magic

---

## Install

**macOS**
```bash
# Install uv via Homebrew (recommended on macOS)
brew install uv

git clone https://github.com/jdetras/PlantOntoMCP.git
cd PlantOntoMCP
make install
```

**Linux**
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh

git clone https://github.com/jdetras/PlantOntoMCP.git
cd PlantOntoMCP
make install
```

**Windows**
```powershell
# Install uv via winget
winget install astral-sh.uv

git clone https://github.com/jdetras/PlantOntoMCP.git
cd PlantOntoMCP
uv sync --extra dev   # make is not available by default on Windows
```

> **Note:** `make` targets are not available on Windows without extra tooling (e.g. Git Bash or WSL).
> Use the equivalent `uv run ...` commands directly, or install [Make for Windows](https://gnuwin32.sourceforge.net/packages/make.htm).

For Jupyter support only:
```bash
uv sync --extra jupyter
```

---

## Quickstart

### Claude Desktop / Claude Code

1. Start the MCP server:
   ```bash
   make serve-mcp
   # or: uv run ontomcp-mcp
   ```

2. Add to your `claude_desktop_config.json`:
   ```json
   {
     "mcpServers": {
       "ontomcp": {
         "command": "uv",
         "args": ["run", "--directory", "/path/to/PlantOntoMCP", "ontomcp-mcp"]
       }
     }
   }
   ```

3. Restart Claude Desktop. All 14 tools appear automatically.

**Try it:** Ask Claude — *"What is the ontology term for plant height?"* — and it will
return `TO:0000207` with definition, synonyms, and an ancestor graph.

---

### GPT / Codex CLI / other MCP clients (SSE)

Claude speaks MCP over stdio; GPT, Codex CLI, and remote clients speak it over
HTTP/SSE. Start OntoMCP in SSE mode — same entrypoint, same 14 tools, switched by
an environment variable:

```bash
ONTOMCP_TRANSPORT=sse make serve-mcp
# or: ONTOMCP_TRANSPORT=sse uv run ontomcp-mcp
# Server starts on http://127.0.0.1:8001
```

Point your OpenAI / Codex client at the SSE endpoint:

```
http://localhost:8001/sse
```

For remote access (non-localhost), set `ONTOMCP_MCP_HOST=0.0.0.0` and ensure the
port is reachable. The default bind is loopback (`127.0.0.1`) so the server is not
network-exposed unless you opt in.

Any MCP-compatible client that speaks the protocol over HTTP/SSE works with the
same endpoint.

---

### HTTP API

```bash
make serve-api
# or: uv run ontomcp-api
```

OpenAPI docs: [http://localhost:8000/docs](http://localhost:8000/docs)

```bash
# Search
curl -X POST localhost:8000/search \
  -H "Content-Type: application/json" \
  -d '{"query": "plant height", "ontologies": ["TO"]}'

# Fetch a term
curl localhost:8000/term/PO:0025034

# Health check
curl localhost:8000/health
```

---

### Jupyter Extension

```bash
make serve-api &   # API must be running
jupyter lab
```

```python
from ontomcp.jupyter_ext import OntoMCPClient, search_panel

search_panel(OntoMCPClient())
```

Type a concept, tick ontologies to restrict the search, and click **Search**.
Each result card has **Copy CURIE** and **Show graph** buttons. In the graph:
- teal = focus term
- gray = ancestor
- purple = descendant
- coral = sibling

Click any node for its term card. Double-click to re-centre the graph on it.

**Annotate a DataFrame column:**

```python
%load_ext ontomcp.jupyter_ext.magic
```
```python
%%ontomcp annotate --df plots --col trait --ontology TO
# adds trait_curie, trait_label, trait_score columns
```

---

## Configuration

| Environment variable   | Default              | Description                     |
|------------------------|----------------------|---------------------------------|
| `ONTOMCP_DB_PATH`      | `~/.ontomcp/cache.db`| SQLite cache file path          |
| `ONTOMCP_API_PORT`     | `8000`               | FastAPI server port             |
| `ONTOMCP_LOG_LEVEL`    | `INFO`               | Logging level                   |
| `ONTOMCP_API_URL`      | `http://localhost:8000` | Jupyter client base URL      |
| `ONTOMCP_TRANSPORT`    | `stdio`              | MCP transport: `stdio` (Claude) or `sse` (GPT/remote) |
| `ONTOMCP_MCP_HOST`     | `127.0.0.1`          | SSE bind address (use `0.0.0.0` to expose) |
| `ONTOMCP_MCP_PORT`     | `8001`               | SSE port (only used when `TRANSPORT=sse`) |
| `AGROPORTAL_API_KEY`   | _(unset)_            | Crop Ontology (AgroPortal) key — optional; CO lookups disabled when unset |

CLI flags override environment variables:
```bash
ontomcp-api --port 9000 --db-path /data/ontomcp.db
ontomcp-mcp --db-path /data/ontomcp.db
```

---

## Ontology Reference

| ID     | Name                                   | Domain                          | Key use case                      |
|--------|----------------------------------------|---------------------------------|-----------------------------------|
| PO     | Plant Ontology                         | Plant anatomy & growth stages   | Tissue / organ / stage annotation |
| TO     | Plant Trait Ontology                   | Phenotypic plant traits         | Crop trait curation, breeding     |
| PECO   | Plant Experimental Conditions Ontology | Treatments & growth conditions  | Experiment & treatment metadata   |
| PPO    | Plant Phenology Ontology               | Phenological growth stages      | Phenology, flowering time         |
| PSO    | Plant Stress Ontology                  | Biotic & abiotic stress         | Stress / tolerance studies        |
| FLOPO  | Flora Phenotype Ontology               | Plant phenotypes from floras    | Botanical phenotype annotation    |
| AGRO   | Agronomy Ontology                      | Agronomic practices & inputs    | Farm management, agronomy         |
| ENVO   | Environment Ontology                   | Environments, biomes, soils     | Site / soil / climate annotation  |
| PCO    | Population and Community Ontology       | Populations & communities       | Germplasm, accessions, diversity  |
| GO     | Gene Ontology                          | Gene function & processes       | Crop genomics, pathway analysis   |
| SO     | Sequence Ontology                      | Genomic sequence features       | Variants, markers, gene models    |

The 11 ontologies above are free and served by the [EBI OLS4 API](https://www.ebi.ac.uk/ols4).
No API key required.

### Crop Ontology (AgroPortal)

The [Crop Ontology](https://cropontology.org) — 42 per-crop trait dictionaries (Rice `CO_320`,
Wheat `CO_321`, Maize `CO_322`, Barley, Sorghum, Banana, Potato, Cassava, Common Bean, Soybean,
Chickpea, Cowpea, …) — is **not** on EBI OLS4. OntoMCP serves it through
[AgroPortal](https://agroportal.eu), which **requires a free API key**:

1. Register at [agroportal.eu/account](https://agroportal.eu/account) and copy your API key.
2. Set it in your environment (or `.env`): `AGROPORTAL_API_KEY=your-key`.

CO terms then resolve through the same tools as everything else — e.g. ask for `CO_320:0000625`
or search `"plant height"` restricted to `["CO_335"]`. A single `search_terms` call transparently
federates EBI OLS4 and AgroPortal and merges the results.

**Without a key**, the 11 OLS4 ontologies work normally and Crop Ontology lookups return a
structured `no_api_key` message. **Note:** AgroPortal models CO trait/method/scale category nodes
with name-based IRIs that carry no CURIE, so CO `get_parents` / `get_children` results can be
sparse; `get_term`, `search`, `validate_term`, and `map_across_ontologies` are unaffected.

### Crop Ontology trait dictionary (variable ↔ trait/method/scale)

AgroPortal's CO snapshot exposes the Trait/Method/Scale/Variable term classes but **not the
relationships linking them**. To get a Variable's full composition — the precise CURIEs needed
for phenotyping annotation — use the trait-dictionary tools, which read the live
[cropontology.org](https://cropontology.org/api_help) BrAPI endpoint (**no API key required**):

- `get_crop_variable("CO_320:0000625")` → the Variable with its `trait`, `method`, and `scale`
  sub-records (each a CURIE + name), plus context of use, growth stage, and scale valid-values.
- `get_crop_trait("CO_320:0000092")` → the Trait and the CURIEs of every Variable that measures it.

These are Crop Ontology only; other CURIEs return `not_crop_ontology` (use `get_term` instead).

---

## Development

```bash
make test              # unit tests (no network)
make test-integration  # requires internet (hits EBI OLS4)
make lint              # ruff lint + format check
make format            # auto-format with ruff
make types             # mypy type check
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for the full contribution guide.

---

## Acknowledgements

PlantOntoMCP is a plant- and crop-focused adaptation of
**[OntoMCP](https://github.com/jeanlouishoneine-tech/OntoMCP)** by
**Jean-Louis Honeine**, which grounds biomedical concepts (GO, MONDO, HPO, ChEBI, …). This fork
keeps the original architecture — the MCP/HTTP servers, the cache-first core, and the Jupyter
extension — and retargets the ontology sources to plant and crop vocabularies (PO, TO, PECO, PPO,
PSO, FLOPO, AGRO, ENVO, PCO, GO, SO), adding the Crop Ontology via AgroPortal as a second backend.
With thanks to the original author and to the [EBI OLS4](https://www.ebi.ac.uk/ols4),
[AgroPortal](https://agroportal.eu), [Planteome](https://planteome.org), and
[Crop Ontology](https://cropontology.org) projects for the open data.

## License

MIT — see [LICENSE](LICENSE). The original copyright (© 2026 Jean-Louis Honeine) is preserved in
the [LICENSE](LICENSE) file, as required.
