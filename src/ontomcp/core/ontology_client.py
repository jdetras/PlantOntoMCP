"""The shared ontology-backend interface.

``OLSClient`` (EBI OLS4), ``AgroPortalClient`` (Crop Ontology), and the
``FederatedClient`` that dispatches between them all expose the same async
surface. Tools accept any of them via this ``OntologyClient`` protocol, so a tool
never needs to know which backend serves a given CURIE.
"""

from typing import Protocol, runtime_checkable


@runtime_checkable
class OntologyClient(Protocol):
    """Structural type for an ontology backend (OLS, AgroPortal, or federated)."""

    async def search(
        self, query: str, ontologies: list[str] | None = None, limit: int = 10
    ) -> list[dict]: ...

    async def fetch_term(self, curie: str) -> dict: ...

    async def fetch_parents(self, curie: str) -> list[dict]: ...

    async def fetch_children(self, curie: str) -> list[dict]: ...

    async def fetch_ancestors(self, curie: str) -> list[dict]: ...

    async def fetch_descendants(self, curie: str) -> list[dict]: ...

    async def fetch_ontology_version(self, ontology: str) -> str | None: ...

    async def aclose(self) -> None: ...
