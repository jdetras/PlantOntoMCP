"""Shared helpers for the tool layer: ontology normalization and client lifecycle.

Kept tiny on purpose. Business logic lives in the individual tool modules.
"""

from contextlib import asynccontextmanager

from ontomcp.core.config import ONTOLOGIES
from ontomcp.core.crop_ontology_client import CropOntologyClient
from ontomcp.core.federated_client import FederatedClient
from ontomcp.core.ols_client import normalize_curie
from ontomcp.core.ontology_client import OntologyClient


def safe_normalize_curie(curie: str) -> tuple[str | None, dict | None]:
    """Normalize a CURIE, returning (normalized, None) or (None, error_dict).

    Tools must never raise; an unparseable CURIE becomes a structured error.
    Callers guard with ``if norm is None: return err_or_default(err), False`` so
    the success path has ``norm`` typed as ``str``.
    """
    try:
        return normalize_curie(curie), None
    except (ValueError, AttributeError) as exc:
        return None, {"error": "bad_curie", "detail": str(exc), "curie": curie}


def normalize_ontologies(ontologies: list[str] | None) -> list[str] | None:
    """Uppercase ontology codes and drop any unknown to the registry.

    Returns None when the input is empty or every code is unknown — callers treat
    None as "search every ontology in the registry".
    """
    if not ontologies:
        return None
    valid = [o.upper() for o in ontologies if o.upper() in ONTOLOGIES]
    return valid or None


@asynccontextmanager
async def ols_client(client: OntologyClient | None):
    """Yield ``client`` if provided, else a fresh ``FederatedClient`` closed on exit.

    Lets every tool accept an optional injected backend (tests, bulk reuse) while
    owning the lifecycle of a default one. The default is federated so a standalone
    tool call routes Crop Ontology CURIEs to AgroPortal and everything else to OLS,
    exactly like the shared client the servers hold.
    """
    if client is not None:
        yield client
        return
    async with FederatedClient() as owned:
        yield owned


@asynccontextmanager
async def crop_client(client: CropOntologyClient | None):
    """Yield ``client`` if provided, else a fresh ``CropOntologyClient`` closed on exit.

    The Crop Ontology trait-dictionary tools talk to the cropontology.org BrAPI
    endpoint, a separate concern from the OLS/AgroPortal term backends, so they
    own their own client lifecycle exactly like ``ols_client`` does.
    """
    if client is not None:
        yield client
        return
    async with CropOntologyClient() as owned:
        yield owned


def is_error(result) -> bool:
    """True if an OLS call returned a structured error (dict, or list of them)."""
    if isinstance(result, dict):
        return "error" in result
    if isinstance(result, list) and result and isinstance(result[0], dict):
        return "error" in result[0]
    return False
