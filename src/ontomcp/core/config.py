"""Single source of truth for ontology registry, OLS settings, paths, and caps.

Later phases import these constants — they must never be redefined elsewhere
(see project CLAUDE.md: "no ad-hoc string building").
"""

import os
from pathlib import Path

from ontomcp import __version__

# --- OLS API ---------------------------------------------------------------

OLS_BASE_URL = "https://www.ebi.ac.uk/ols4/api"
USER_AGENT = f"OntoMCP/{__version__}"

# OLS client retry/timeout. Retry only on 429 + 5xx; max 3 attempts.
OLS_TIMEOUT_SECONDS = 10.0
OLS_MAX_RETRIES = 3
OLS_BACKOFF_BASE = 0.5  # seconds; sleep = base * 2 ** (attempt - 1)
OLS_RETRY_STATUS = (429, 500, 502, 503, 504)

# --- Ontology registry (v1) ------------------------------------------------
# Free plant & crop ontologies served via the EBI OLS4 API. No API key required.

# ``slug`` is the lowercase ontology id OLS uses in URL paths and the search
# filter. For every ontology below it equals the lowercased registry key, but it
# is stored explicitly so a future ontology whose slug differs from its CURIE
# prefix has a single source of truth.
ONTOLOGIES: dict[str, dict[str, str]] = {
    "PO": {
        "name": "Plant Ontology",
        "domain": "Plant anatomy and developmental growth stages",
        "slug": "po",
    },
    "TO": {
        "name": "Plant Trait Ontology",
        "domain": "Phenotypic traits of plants (the primary crop-trait vocabulary)",
        "slug": "to",
    },
    "PECO": {
        "name": "Plant Experimental Conditions Ontology",
        "domain": "Treatments, growth conditions, and experimental factors",
        "slug": "peco",
    },
    "PPO": {
        "name": "Plant Phenology Ontology",
        "domain": "Phenological (seasonal) growth stages and events",
        "slug": "ppo",
    },
    "PSO": {
        "name": "Plant Stress Ontology",
        "domain": "Biotic and abiotic plant stresses",
        "slug": "pso",
    },
    "FLOPO": {
        "name": "Flora Phenotype Ontology",
        "domain": "Plant phenotypes and traits from botanical floras",
        "slug": "flopo",
    },
    "AGRO": {
        "name": "Agronomy Ontology",
        "domain": "Agronomic practices, inputs, and farm management",
        "slug": "agro",
    },
    "ENVO": {
        "name": "Environment Ontology",
        "domain": "Environments, biomes, soils, and habitats",
        "slug": "envo",
    },
    "PCO": {
        "name": "Population and Community Ontology",
        "domain": "Populations, communities, and their attributes",
        "slug": "pco",
    },
    "GO": {
        "name": "Gene Ontology",
        "domain": "Gene function and biological processes (cross-kingdom; crop genomics)",
        "slug": "go",
    },
    "SO": {
        "name": "Sequence Ontology",
        "domain": "Genomic sequence features and types (genes, exons, variants)",
        "slug": "so",
    },
}

# Full OBO IRI templates per ontology. CURIE id fills the {id} slot, then the
# result is double-URL-encoded when used as an OLS path parameter. Every plant
# ontology here mints standard OBO PURLs, so the prefix maps 1:1 to the template.
IRI_TEMPLATES: dict[str, str] = {
    "PO": "http://purl.obolibrary.org/obo/PO_{id}",
    "TO": "http://purl.obolibrary.org/obo/TO_{id}",
    "PECO": "http://purl.obolibrary.org/obo/PECO_{id}",
    "PPO": "http://purl.obolibrary.org/obo/PPO_{id}",
    "PSO": "http://purl.obolibrary.org/obo/PSO_{id}",
    "FLOPO": "http://purl.obolibrary.org/obo/FLOPO_{id}",
    "AGRO": "http://purl.obolibrary.org/obo/AGRO_{id}",
    "ENVO": "http://purl.obolibrary.org/obo/ENVO_{id}",
    "PCO": "http://purl.obolibrary.org/obo/PCO_{id}",
    "GO": "http://purl.obolibrary.org/obo/GO_{id}",
    "SO": "http://purl.obolibrary.org/obo/SO_{id}",
}

# --- AgroPortal / Crop Ontology backend ------------------------------------
# The Crop Ontology (CO) is not on EBI OLS4; its per-crop trait dictionaries are
# served by AgroPortal (an OntoPortal/BioPortal instance). Unlike OLS4, AgroPortal
# REQUIRES an API key (free, from https://agroportal.eu/account). Set it via the
# AGROPORTAL_API_KEY env var; when unset, Crop Ontology lookups return a structured
# ``no_api_key`` error and the OLS-backed ontologies keep working unaffected.

AGROPORTAL_BASE_URL = "https://data.agroportal.eu"
AGROPORTAL_API_KEY = os.environ.get("AGROPORTAL_API_KEY")
# Crop Ontology class IRIs look like ``https://cropontology.org/rdf/CO_320:0000625``
# (the CURIE is the IRI tail), so the template embeds the acronym and {id} = local id.
AGROPORTAL_CLASS_IRI_BASE = "https://cropontology.org/rdf/"

# Crop Ontology per-crop ontologies on AgroPortal (acronym -> display name). The
# acronym (e.g. ``CO_320``) is both the registry key and the CURIE prefix.
CROP_ONTOLOGIES: dict[str, str] = {
    "CO_020": "Multi-Crop Passport Ontology",
    "CO_121": "Wheat Plant Anatomy and Development Ontology",
    "CO_125": "Banana Anatomy Ontology",
    "CO_320": "Rice Ontology",
    "CO_321": "Wheat Ontology",
    "CO_322": "Maize Ontology",
    "CO_323": "Barley Ontology",
    "CO_324": "Sorghum Ontology",
    "CO_325": "Banana Ontology",
    "CO_326": "Coconut Ontology",
    "CO_327": "Pearl Millet Ontology",
    "CO_330": "Potato Ontology",
    "CO_331": "Sweet Potato Ontology",
    "CO_333": "Beet Ontology",
    "CO_334": "Cassava Ontology",
    "CO_335": "Common Bean Ontology",
    "CO_336": "Soybean Ontology",
    "CO_337": "Groundnut Ontology",
    "CO_338": "Chickpea Ontology",
    "CO_339": "Lentil Ontology",
    "CO_340": "Cowpea Ontology",
    "CO_341": "Pigeonpea Ontology",
    "CO_343": "Yam Ontology",
    "CO_345": "Brachiaria Ontology",
    "CO_346": "Mungbean Ontology",
    "CO_347": "Castor Bean Ontology",
    "CO_348": "Brassica Ontology",
    "CO_350": "Oat Ontology",
    "CO_356": "Vitis Ontology",
    "CO_357": "Woody Plant Ontology",
    "CO_358": "Cotton Ontology",
    "CO_359": "Sunflower Ontology",
    "CO_360": "Sugar Kelp Ontology",
    "CO_365": "Fababean Ontology",
    "CO_366": "Bambara Groundnut Ontology",
    "CO_367": "Quinoa Ontology",
    "CO_369": "Sainfoin Ontology",
    "CO_370": "Apple Ontology",
    "CO_371": "Blueberry Ontology",
    "CO_372": "Strawberry Ontology",
    "CO_374": "Red Clover Ontology",
    "CO_715": "Crop Research Ontology",
}

# Merge the Crop Ontology dictionaries into the shared registry so every tool,
# the cache, and /health treat them like any other ontology. They are tagged
# ``source="agroportal"`` so the federated client routes them to AgroPortal; all
# other entries default to ``source="ols"`` (see ``ontology_source``).
for _acr, _name in CROP_ONTOLOGIES.items():
    ONTOLOGIES[_acr] = {
        "name": _name,
        "domain": f"Crop Ontology — {_name} traits, variables, methods, and scales",
        "slug": _acr,
        "source": "agroportal",
    }
    IRI_TEMPLATES[_acr] = f"{AGROPORTAL_CLASS_IRI_BASE}{_acr}:{{id}}"


def ontology_source(prefix: str) -> str:
    """Return the backend for an ontology prefix: ``"agroportal"`` or ``"ols"``.

    Prefixes default to ``"ols"`` (the EBI OLS4 backend); only the Crop Ontology
    entries carry an explicit ``source="agroportal"``. Unknown prefixes fall back
    to ``"ols"`` so the existing behaviour is unchanged.
    """
    meta = ONTOLOGIES.get(prefix.upper())
    return meta.get("source", "ols") if meta else "ols"


# --- Cache -----------------------------------------------------------------

# Override with ONTOMCP_DB_PATH; defaults to a file in the user's home dir.
# Expand ~ in the path (handles env vars like "~/.ontomcp/cache.db").
DB_PATH = Path(
    os.environ.get("ONTOMCP_DB_PATH", Path.home() / ".ontomcp" / "cache.db")
).expanduser()

# Re-fetch any term older than this. validate_term never uses the cache.
CACHE_TTL_DAYS = 7

# SQLite busy timeout (ms). Both servers write through the shared core, so a
# second writer must wait for the WAL write lock rather than fail immediately.
BUSY_TIMEOUT_MS = 5000

# --- Transport -------------------------------------------------------------
# stdio (default) serves Claude Desktop / Claude Code; sse serves GPT, Codex
# CLI, and remote MCP clients. Host/port apply only in sse mode. Default bind
# is loopback — set ONTOMCP_MCP_HOST=0.0.0.0 to expose on the network.

MCP_TRANSPORT = os.environ.get("ONTOMCP_TRANSPORT", "stdio")
MCP_HOST = os.environ.get("ONTOMCP_MCP_HOST", "127.0.0.1")
MCP_PORT = int(os.environ.get("ONTOMCP_MCP_PORT", "8001"))

# --- Payload caps ----------------------------------------------------------
# Enforced by the tools; keep ontology subgraphs small enough for chat payloads.

DESCENDANTS_CAP = 50  # get_descendants hard cap
GRAPH_NODE_CAP = 40  # get_term_graph hard cap
BULK_WARN = 100  # bulk_annotate: warn above this many input terms
BULK_MAX = 500  # bulk_annotate: hard error above this many input terms
SEARCH_LIMIT_MAX = 100  # search_terms: upper bound on requested result rows


# --- Search relevance score ------------------------------------------------


def rank_score(index: int, total: int) -> float:
    """Map a result's position in relevance order to a consistent 0–1 score.

    Both search paths (cache FTS and live OLS) return results best-first but on
    incomparable native scales (FTS bm25 vs. Solr score). To give callers a single
    comparable signal, ``search_terms`` reports this rank-normalized score instead:
    the top hit scores highest, decreasing monotonically, identical regardless of
    source. It is ordinal — a relative ranking within one result set, not an
    absolute match strength.

    ``index`` is 0-based; ``total`` is the result count. Returns 0.0 if total <= 0.
    """
    if total <= 0:
        return 0.0
    return round((total - index) / total, 3)
