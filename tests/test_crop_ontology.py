"""Unit tests for the Crop Ontology BrAPI client and trait-dictionary tools.

httpx is mocked via MockTransport — no network. Covers the variable/trait
parsers, the cache-first tool path with write-back, and the routing guards.
Live-endpoint checks are marked ``integration`` and skipped offline.
"""

import httpx
import pytest

from ontomcp.core import cache, config
from ontomcp.core.crop_ontology_client import CropOntologyClient
from ontomcp.core.tools import get_crop_trait, get_crop_variable

_VARIABLE = {
    "observationVariableDbId": "CO_320:0000625",
    "name": "AP_Lab_1to9",
    "synonyms": ["AP"],
    "contextOfUse": ["Breeding"],
    "growthStage": "flowering",
    "status": "recommended",
    "crop": "Rice",
    "institution": "IRRI",
    "scientist": "Jeffrey Detras",
    "date": None,
    "language": "EN",
    "defaultValue": None,
    "trait": {
        "traitDbId": "CO_320:0000092",
        "name": "Abortion pattern",
        "class": "Phenological",
        "description": "Describes the stage at which pollen grains abort.",
    },
    "method": {
        "methodDbId": "CO_320:0000330",
        "name": "Abortion pattern estimation",
        "class": "Estimation",
        "description": "Collect florets and fix in solution.",
    },
    "scale": {
        "scaleDbId": "CO_320:0000331",
        "name": "abortion pattern scale",
        "dataType": "Nominal",
        "validValues": {"min": None, "max": None, "categories": ["1= Pollen free"]},
    },
}

_TRAIT = {
    "traitDbId": "CO_320:0000092",
    "traitId": "AP",
    "name": "Abortion pattern",
    "defaultValue": None,
    "observationVariables": [{"observationVariableDbId": "CO_320:0000625"}],
}


def _envelope(result):
    return httpx.Response(200, json={"metadata": {"status": []}, "result": result})


def _client(handler) -> CropOntologyClient:
    transport = httpx.MockTransport(handler)
    http = httpx.AsyncClient(base_url=config.CROPONTOLOGY_BASE_URL, transport=transport)
    return CropOntologyClient(client=http)


def _handler(request):
    path = request.url.path
    if "/variables/CO_320:0000625" in path:
        return _envelope(_VARIABLE)
    if "/traits/CO_320:0000092" in path:
        return _envelope(_TRAIT)
    # Unknown id: BrAPI returns 200 with an empty result.
    return _envelope({})


# --- client parsers --------------------------------------------------------


async def test_fetch_variable_parses_trait_method_scale_triple():
    async with _client(_handler) as cli:
        v = await cli.fetch_variable("CO_320:0000625")
    assert v["curie"] == "CO_320:0000625"
    assert v["label"] == "AP_Lab_1to9"
    assert v["trait"] == {
        "curie": "CO_320:0000092",
        "name": "Abortion pattern",
        "class": "Phenological",
        "description": "Describes the stage at which pollen grains abort.",
    }
    assert v["method"]["curie"] == "CO_320:0000330"
    assert v["scale"]["curie"] == "CO_320:0000331"
    assert v["scale"]["data_type"] == "Nominal"
    assert v["scale"]["valid_values"]["categories"] == ["1= Pollen free"]
    assert v["context_of_use"] == ["Breeding"]


async def test_fetch_variable_not_found_on_empty_result():
    async with _client(_handler) as cli:
        v = await cli.fetch_variable("CO_320:9999999")
    assert v == {"error": "not_found", "curie": "CO_320:9999999"}


async def test_fetch_trait_lists_variables():
    async with _client(_handler) as cli:
        t = await cli.fetch_trait("CO_320:0000092")
    assert t["curie"] == "CO_320:0000092"
    assert t["trait_id"] == "AP"
    assert t["variables"] == ["CO_320:0000625"]


# --- tool: cache-first + guards --------------------------------------------


async def test_get_crop_variable_cache_first_with_writeback(tmp_db_path):
    cache.init_db(tmp_db_path)
    calls = {"n": 0}

    def counting(request):
        calls["n"] += 1
        return _handler(request)

    # First call: cache miss -> BrAPI fetch -> write-back.
    result, hit = await get_crop_variable(
        "CO_320:0000625", db_path=tmp_db_path, client=_client(counting)
    )
    assert hit is False
    assert result["trait"]["curie"] == "CO_320:0000092"
    assert calls["n"] == 1

    # Second call: served from cache, no network. Handler raises if hit.
    def boom(request):
        raise AssertionError("cache hit must not touch the network")

    result2, hit2 = await get_crop_variable(
        "CO_320:0000625", db_path=tmp_db_path, client=_client(boom)
    )
    assert hit2 is True
    assert result2["trait"]["curie"] == "CO_320:0000092"
    assert result2 == result  # identical shape hit-or-miss


async def test_get_crop_variable_rejects_non_crop_ontology(tmp_db_path):
    cache.init_db(tmp_db_path)

    def boom(request):
        raise AssertionError("a non-CO CURIE must not reach BrAPI")

    result, hit = await get_crop_variable("PO:0025034", db_path=tmp_db_path, client=_client(boom))
    assert hit is False
    assert result["error"] == "not_crop_ontology"


async def test_get_crop_variable_bad_curie(tmp_db_path):
    cache.init_db(tmp_db_path)
    result, hit = await get_crop_variable(
        "not a curie", db_path=tmp_db_path, client=_client(_handler)
    )
    assert hit is False
    assert result["error"] == "bad_curie"


async def test_get_crop_trait_cache_first(tmp_db_path):
    cache.init_db(tmp_db_path)
    result, hit = await get_crop_trait(
        "CO_320:0000092", db_path=tmp_db_path, client=_client(_handler)
    )
    assert hit is False
    assert result["variables"] == ["CO_320:0000625"]

    def boom(request):
        raise AssertionError("cache hit must not touch the network")

    result2, hit2 = await get_crop_trait(
        "CO_320:0000092", db_path=tmp_db_path, client=_client(boom)
    )
    assert hit2 is True
    assert result2 == result


# --- integration (live cropontology.org BrAPI, skipped offline) ------------


@pytest.mark.integration
async def test_live_fetch_variable_triple():
    async with CropOntologyClient() as cli:
        v = await cli.fetch_variable("CO_320:0000625")
    assert v.get("curie") == "CO_320:0000625"
    assert v["trait"]["curie"].startswith("CO_320:")
    assert v["method"]["curie"].startswith("CO_320:")
    assert v["scale"]["curie"].startswith("CO_320:")


@pytest.mark.integration
async def test_live_fetch_trait():
    async with CropOntologyClient() as cli:
        t = await cli.fetch_trait("CO_320:0000092")
    assert t.get("curie") == "CO_320:0000092"
    assert isinstance(t.get("variables"), list)
