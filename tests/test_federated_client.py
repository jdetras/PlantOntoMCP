"""Unit tests for the FederatedClient backend router. httpx is mocked — no network."""

import httpx

from ontomcp.core import config
from ontomcp.core.agroportal_client import AgroPortalClient
from ontomcp.core.federated_client import FederatedClient
from ontomcp.core.ols_client import OLSClient


def _ols(handler) -> OLSClient:
    transport = httpx.MockTransport(handler)
    http = httpx.AsyncClient(base_url=config.OLS_BASE_URL, transport=transport)
    return OLSClient(client=http)


def _agro(handler, api_key="testkey") -> AgroPortalClient:
    transport = httpx.MockTransport(handler)
    http = httpx.AsyncClient(base_url=config.AGROPORTAL_BASE_URL, transport=transport)
    return AgroPortalClient(api_key=api_key, client=http)


def _ols_term(request):
    return httpx.Response(
        200, json={"_embedded": {"terms": [{"obo_id": "PO:0025034", "label": "leaf"}]}}
    )


def _agro_term(request):
    return httpx.Response(
        200,
        json={
            "@id": "https://cropontology.org/rdf/CO_320:0000625",
            "prefLabel": "rice variable",
            "definition": [],
            "synonym": [],
            "obsolete": False,
        },
    )


# --- single-CURIE routing --------------------------------------------------


async def test_fetch_term_routes_ols_vs_agroportal():
    ols_hits = {"n": 0}
    agro_hits = {"n": 0}

    def ols_handler(r):
        ols_hits["n"] += 1
        return _ols_term(r)

    def agro_handler(r):
        agro_hits["n"] += 1
        return _agro_term(r)

    fed = FederatedClient(ols=_ols(ols_handler), agroportal=_agro(agro_handler))
    async with fed:
        plant = await fed.fetch_term("PO:0025034")
        crop = await fed.fetch_term("CO_320:0000625")

    assert plant["curie"] == "PO:0025034"
    assert crop["curie"] == "CO_320:0000625"
    # Each backend was hit exactly once, by the CURIE that belongs to it.
    assert ols_hits["n"] == 1
    assert agro_hits["n"] == 1


async def test_hierarchy_routes_crop_curie_to_agroportal():
    def ols_handler(r):  # pragma: no cover - a CO CURIE must not reach OLS
        raise AssertionError("CO CURIE must not route to OLS")

    def agro_handler(r):
        return httpx.Response(
            200, json=[{"@id": "https://cropontology.org/rdf/CO_320:0000700", "prefLabel": "x"}]
        )

    fed = FederatedClient(ols=_ols(ols_handler), agroportal=_agro(agro_handler))
    async with fed:
        parents = await fed.fetch_parents("CO_320:0000625")
    assert parents == [{"curie": "CO_320:0000700", "label": "x", "rel_type": "is_a"}]


# --- search partition + merge ----------------------------------------------


async def test_search_merges_both_backends():
    def ols_handler(r):
        return httpx.Response(
            200, json={"response": {"docs": [{"obo_id": "PO:0025034", "label": "leaf"}]}}
        )

    def agro_handler(r):
        return httpx.Response(
            200,
            json={
                "collection": [
                    {
                        "@id": "https://cropontology.org/rdf/CO_320:0000625",
                        "prefLabel": "rice height",
                        "definition": [],
                        "synonym": [],
                        "obsolete": False,
                    }
                ]
            },
        )

    fed = FederatedClient(ols=_ols(ols_handler), agroportal=_agro(agro_handler))
    async with fed:
        results = await fed.search("height", ["PO", "CO_320"], limit=10)

    curies = {r["curie"] for r in results}
    assert curies == {"PO:0025034", "CO_320:0000625"}
    # Merged list is rank-normalized: top hit scores 1.0, scores strictly decreasing.
    scores = [r["score"] for r in results]
    assert scores[0] == 1.0
    assert scores == sorted(scores, reverse=True)


async def test_search_skips_agroportal_when_only_ols_requested():
    def ols_handler(r):
        return httpx.Response(
            200, json={"response": {"docs": [{"obo_id": "PO:0025034", "label": "leaf"}]}}
        )

    def agro_handler(r):  # pragma: no cover - must not be called
        raise AssertionError("AgroPortal must not be queried for an OLS-only search")

    fed = FederatedClient(ols=_ols(ols_handler), agroportal=_agro(agro_handler))
    async with fed:
        results = await fed.search("leaf", ["PO"], limit=10)
    assert [r["curie"] for r in results] == ["PO:0025034"]


async def test_unfiltered_search_scopes_ols_to_registry():
    # ontologies=None must scope the OLS leg to the registry's OLS ontologies,
    # never query all of OLS4 unfiltered (which would return out-of-registry terms).
    seen = {}

    def ols_handler(r):
        seen["ontology"] = r.url.params.get("ontology")
        return httpx.Response(
            200, json={"response": {"docs": [{"obo_id": "PO:0025034", "label": "leaf"}]}}
        )

    def agro_handler(r):
        return httpx.Response(200, json={"collection": []})

    fed = FederatedClient(ols=_ols(ols_handler), agroportal=_agro(agro_handler))
    async with fed:
        await fed.search("leaf", None, limit=10)

    assert seen["ontology"] is not None, "OLS search must carry an ontology filter"
    sent = set(seen["ontology"].split(","))
    expected = {config.ONTOLOGIES[k]["slug"] for k in config.OLS_ONTOLOGIES}
    assert sent == expected
    # No Crop Ontology slug leaks into the OLS filter.
    assert all(not s.startswith("co_") for s in sent)


async def test_search_without_key_uses_ols_only():
    def ols_handler(r):
        return httpx.Response(
            200, json={"response": {"docs": [{"obo_id": "PO:0025034", "label": "leaf"}]}}
        )

    def agro_handler(r):  # pragma: no cover - keyless AgroPortal never hits network
        raise AssertionError("keyless AgroPortal must not hit the network")

    # api_key="" -> no key; CO is skipped, OLS still serves results.
    fed = FederatedClient(ols=_ols(ols_handler), agroportal=_agro(agro_handler, api_key=""))
    async with fed:
        results = await fed.search("leaf", None, limit=10)
    assert [r["curie"] for r in results] == ["PO:0025034"]
