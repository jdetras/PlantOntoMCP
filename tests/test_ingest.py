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
    assert res == {"ontology": "CO_320", "ingested": 2}  # root skipped

    # The term AgroPortal could not search is now found via our own FTS index.
    hits, cache_hit = await search_terms("plant height", ["CO_320"], db_path=tmp_db_path)
    assert cache_hit is True
    assert "CO_320:0000076" in {h["curie"] for h in hits}


async def test_ingest_rejects_non_crop_ontology(tmp_db_path):
    res = await ingest_crop_ontology("PO", db_path=tmp_db_path, client=None)
    assert res["error"] == "not_crop_ontology"


async def test_ingest_keyless_returns_error(tmp_db_path):
    res = await ingest_crop_ontology(
        "CO_320", db_path=tmp_db_path, client=_agro(lambda r: httpx.Response(200), api_key="")
    )
    assert res["error"] == "no_api_key"
