"""Crop Ontology trait-dictionary routes (cropontology.org BrAPI backend).

Thin HTTP surface over the get_crop_variable / get_crop_trait core tools — no
business logic here (project rule).
"""

from fastapi import APIRouter, Depends

from ontomcp.api.responses import get_crop_client, get_db_path, respond
from ontomcp.core.crop_ontology_client import CropOntologyClient
from ontomcp.core.tools import get_crop_trait, get_crop_variable

router = APIRouter()


@router.get("/crop/variable/{curie}")
async def crop_variable(
    curie: str,
    client: CropOntologyClient = Depends(get_crop_client),
    db_path=Depends(get_db_path),
):
    result, cached = await get_crop_variable(curie, db_path=db_path, client=client)
    return respond(result, cached)


@router.get("/crop/trait/{curie}")
async def crop_trait(
    curie: str,
    client: CropOntologyClient = Depends(get_crop_client),
    db_path=Depends(get_db_path),
):
    result, cached = await get_crop_trait(curie, db_path=db_path, client=client)
    return respond(result, cached)
