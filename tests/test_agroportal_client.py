"""Unit tests for the AgroPortal (Crop Ontology) client. httpx is mocked — no network."""

import httpx
import pytest

from ontomcp.core import config
from ontomcp.core.agroportal_client import AgroPortalClient


def _client(handler, api_key="testkey") -> AgroPortalClient:
    """AgroPortalClient wired to a MockTransport handler (no network)."""
    transport = httpx.MockTransport(handler)
    http = httpx.AsyncClient(
        base_url=config.AGROPORTAL_BASE_URL,
        transport=transport,
        headers={"User-Agent": config.USER_AGENT},
    )
    return AgroPortalClient(api_key=api_key, client=http)


def _class_obj(
    curie="CO_320:0000625", label="Plant height", definition=None, synonyms=None, obs=False
):
    return {
        "@id": f"https://cropontology.org/rdf/{curie}",
        "prefLabel": label,
        "definition": definition if definition is not None else [],
        "synonym": synonyms if synonyms is not None else [],
        "obsolete": obs,
        "links": {"children": "x", "parents": "y"},
    }


# --- no API key (offline, structured error) --------------------------------


async def test_no_key_short_circuits_every_method():
    # api_key="" -> has_key False regardless of the environment.
    async def handler(request):  # pragma: no cover - must never be hit
        raise AssertionError("no network may happen without an API key")

    async with _client(handler, api_key="") as c:
        assert not c.has_key
        search = await c.search("plant height", ["CO_320"])
        term = await c.fetch_term("CO_320:0000625")
        parents = await c.fetch_parents("CO_320:0000625")
        version = await c.fetch_ontology_version("CO_320")

    assert search[0]["error"] == "no_api_key"
    assert term["error"] == "no_api_key"
    assert parents[0]["error"] == "no_api_key"
    assert version is None  # version capture is best-effort, never an error


# --- search ----------------------------------------------------------------


async def test_search_parses_collection_and_derives_curie():
    def handler(request):
        body = {
            "collection": [
                _class_obj("CO_320:0000625", "Plant height", definition=["height of plant"]),
                _class_obj("CO_320:0000700", "Grain yield"),
            ]
        }
        return httpx.Response(200, json=body)

    async with _client(handler) as c:
        results = await c.search("height", ["CO_320"], limit=5)

    assert [r["curie"] for r in results] == ["CO_320:0000625", "CO_320:0000700"]
    assert results[0]["ontology"] == "CO_320"
    assert results[0]["definition"] == "height of plant"
    # Rank-normalized score, best first (same scale as the OLS path).
    assert results[0]["score"] == 1.0
    assert results[1]["score"] == 0.5


async def test_search_filters_to_requested_ontologies_client_side():
    # AgroPortal's ontologies filter is loose, so a foreign-ontology hit must be
    # dropped client-side.
    def handler(request):
        body = {
            "collection": [
                _class_obj("CO_335:0000932", "Plant height"),  # not requested
                _class_obj("CO_320:0000625", "Plant height"),  # requested
            ]
        }
        return httpx.Response(200, json=body)

    async with _client(handler) as c:
        results = await c.search("plant height", ["CO_320"])
    assert [r["curie"] for r in results] == ["CO_320:0000625"]


# --- fetch_term ------------------------------------------------------------


async def test_fetch_term_parses_class_single_encoded():
    seen = {}

    def handler(request):
        seen["raw"] = request.url.raw_path.decode()
        obj = _class_obj(synonyms=["PH", "height"], definition=["the height"])
        return httpx.Response(200, json=obj)

    async with _client(handler) as c:
        term = await c.fetch_term("CO_320:0000625")

    assert term["curie"] == "CO_320:0000625"
    assert term["ontology"] == "CO_320"
    assert term["label"] == "Plant height"
    assert term["definition"] == "the height"
    assert term["synonyms"]["exact"] == ["PH", "height"]
    # Single-encoded IRI on the wire (':' -> '%3A', not the OLS double '%253A').
    assert "%3A" in seen["raw"] and "%253A" not in seen["raw"]
    assert "/ontologies/CO_320/classes/" in seen["raw"]


async def test_fetch_term_not_found():
    async with _client(lambda r: httpx.Response(404)) as c:
        result = await c.fetch_term("CO_320:9999999")
    assert result == {"error": "not_found", "curie": "CO_320:9999999"}


# --- hierarchy -------------------------------------------------------------


async def test_fetch_parents_bare_list_tagged_is_a():
    def handler(request):
        assert request.url.path.endswith("/parents")
        return httpx.Response(
            200,
            json=[{"@id": "https://cropontology.org/rdf/Variable", "prefLabel": "Variable"}],
        )

    async with _client(handler) as c:
        nodes = await c.fetch_parents("CO_320:0000625")
    # "Variable" has no CURIE-shaped @id, so it is dropped (unparseable).
    assert nodes == []


async def test_fetch_descendants_paged_collection_tagged_descendant():
    def handler(request):
        assert request.url.path.endswith("/descendants")
        body = {
            "collection": [
                {"@id": "https://cropontology.org/rdf/CO_320:0000700", "prefLabel": "child"}
            ]
        }
        return httpx.Response(200, json=body)

    async with _client(handler) as c:
        nodes = await c.fetch_descendants("CO_320:0000625")
    assert nodes == [{"curie": "CO_320:0000700", "label": "child", "rel_type": "descendant"}]


# --- integration (live AgroPortal, skipped offline / without a key) ---------


@pytest.mark.integration
async def test_live_fetch_co_term():
    if not config.AGROPORTAL_API_KEY:
        pytest.skip("AGROPORTAL_API_KEY not set")
    async with AgroPortalClient() as c:
        term = await c.fetch_term("CO_320:0000625")
    assert term.get("curie") == "CO_320:0000625"
    assert term.get("label")
