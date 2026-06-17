"""Unit tests for Crop Ontology ingestion. httpx mocked — no network.

Covers paging AgroPortal classes into the FTS cache and the resulting
searchability, plus the not-a-crop-ontology guard.
"""

import httpx

from ontomcp.core import config
from ontomcp.core.agroportal_client import AgroPortalClient
from ontomcp.core.ingest import ingest_crop_ontology
from ontomcp.core.tools import search_terms

_CLASSES_PAGE = {
    "collection": [
        {
            "@id": "https://cropontology.org/rdf/CO_320:0000076",
            "prefLabel": "Plant height",
            "definition": ["Height of the plant from soil to top."],
        },
        {
            "@id": "https://cropontology.org/rdf/CO_320:0000479",
            "prefLabel": "Plant height measurement",
            "definition": [],
        },
        # Root node has no parseable CURIE -> must be skipped.
        {"@id": "https://cropontology.org/rdf/Variable", "prefLabel": "Variable"},
        # Bare category node: underscore-misparses to "ABIOTIC:stress" (not a
        # registry ontology) -> must be dropped, not ingested as a junk row.
        {"@id": "https://cropontology.org/rdf/Abiotic_stress", "prefLabel": "Abiotic_stress"},
    ],
    "pageCount": 1,
    "page": 1,
}


def _agro(handler, api_key="testkey") -> AgroPortalClient:
    transport = httpx.MockTransport(handler)
    http = httpx.AsyncClient(base_url=config.AGROPORTAL_BASE_URL, transport=transport)
    return AgroPortalClient(api_key=api_key, client=http)


async def test_ingest_populates_fts_and_makes_terms_searchable(tmp_db_path):
    def handler(request):
        assert "/ontologies/CO_320/classes" in request.url.path
        return httpx.Response(200, json=_CLASSES_PAGE)

    res = await ingest_crop_ontology("CO_320", db_path=tmp_db_path, client=_agro(handler))
    assert res == {"ontology": "CO_320", "ingested": 2}  # root + junk category node skipped

    # The term AgroPortal could not search is now found via our own FTS index.
    hits, cache_hit = await search_terms("plant height", ["CO_320"], db_path=tmp_db_path)
    assert cache_hit is True
    assert "CO_320:0000076" in {h["curie"] for h in hits}

    # The misparsed category node was not ingested as a junk-ontology row.
    found = await search_terms("Abiotic_stress", ["CO_320"], db_path=tmp_db_path)
    assert all(h["ontology"] in config.ONTOLOGIES for h in found[0])


async def test_search_terms_lazy_ingests_scoped_crop(tmp_db_path):
    from ontomcp.core import cache

    cache.init_db(tmp_db_path)
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        return httpx.Response(200, json=_CLASSES_PAGE)

    # CO_320 not ingested yet -> the scoped search lazily ingests it, then finds it.
    hits, _ = await search_terms(
        "plant height", ["CO_320"], db_path=tmp_db_path, ingest_client=_agro(handler)
    )
    assert calls["n"] >= 1
    assert "CO_320:0000076" in {h["curie"] for h in hits}

    # Second scoped search: ingest marker is fresh -> no re-ingest (handler raises if hit).
    def boom(request):
        raise AssertionError("fresh ingest must not be repeated")

    hits2, _ = await search_terms(
        "plant height", ["CO_320"], db_path=tmp_db_path, ingest_client=_agro(boom)
    )
    assert "CO_320:0000076" in {h["curie"] for h in hits2}


async def test_search_terms_skips_ingest_for_ols_scope(tmp_db_path):
    from ontomcp.core import cache
    from ontomcp.core.ols_client import OLSClient

    cache.init_db(tmp_db_path)

    def boom(request):
        raise AssertionError("an OLS-scoped search must not trigger a CO ingest")

    ols = OLSClient(
        client=httpx.AsyncClient(
            base_url=config.OLS_BASE_URL,
            transport=httpx.MockTransport(
                lambda r: httpx.Response(200, json={"response": {"docs": []}})
            ),
        )
    )
    # Scope to PO (an OLS ontology): the lazy CO-ingest path must be skipped.
    hits, _ = await search_terms(
        "leaf", ["PO"], db_path=tmp_db_path, ingest_client=_agro(boom), client=ols
    )
    assert hits == []


async def test_ingest_rejects_non_crop_ontology(tmp_db_path):
    res = await ingest_crop_ontology("PO", db_path=tmp_db_path, client=None)
    assert res["error"] == "not_crop_ontology"


async def test_ingest_keyless_returns_error(tmp_db_path):
    res = await ingest_crop_ontology(
        "CO_320", db_path=tmp_db_path, client=_agro(lambda r: httpx.Response(200), api_key="")
    )
    assert res["error"] == "no_api_key"
