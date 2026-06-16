"""Federated ontology client: routes each lookup to the right backend.

OntoMCP serves two backends — EBI OLS4 for the plant/genomics ontologies and
AgroPortal for the Crop Ontology (CO). This client implements the
``OntologyClient`` surface and dispatches by ontology source:

- single-CURIE calls (``fetch_term`` / hierarchy / version) route to the backend
  that owns the CURIE's prefix (``config.ontology_source``);
- ``search`` partitions the requested ontologies by source, queries each backend,
  and merges the results into one rank-normalized list.

The servers hold ONE ``FederatedClient`` for the process lifetime, exactly where
they previously held an ``OLSClient`` — tools are unchanged. When no AgroPortal
API key is configured, CO is simply skipped in search and CO CURIE lookups return
the AgroPortal client's structured ``no_api_key`` error; the OLS path is untouched.
"""

import asyncio

from ontomcp.core import config
from ontomcp.core.agroportal_client import AgroPortalClient
from ontomcp.core.config import rank_score
from ontomcp.core.ols_client import OLSClient, normalize_curie


def _is_error_list(value: list) -> bool:
    """True if a backend returned a structured error list."""
    return bool(value) and isinstance(value[0], dict) and "error" in value[0]


class FederatedClient:
    """Dispatch ontology lookups to OLS or AgroPortal by ontology source."""

    def __init__(
        self,
        ols: OLSClient | None = None,
        agroportal: AgroPortalClient | None = None,
    ) -> None:
        self._owns_ols = ols is None
        self._owns_agro = agroportal is None
        self._ols = ols or OLSClient()
        self._agro = agroportal or AgroPortalClient()

    async def __aenter__(self) -> "FederatedClient":
        return self

    async def __aexit__(self, *exc) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        if self._owns_ols:
            await self._ols.aclose()
        if self._owns_agro:
            await self._agro.aclose()

    @property
    def has_key(self) -> bool:
        """The federated backend can always reach OLS, so it is always usable."""
        return True

    # --- routing ----------------------------------------------------------

    def _backend_for(self, curie: str):
        """Return the backend that owns ``curie`` (by its prefix's source)."""
        try:
            prefix = normalize_curie(curie).split(":", 1)[0]
        except (ValueError, AttributeError):
            return self._ols  # let the OLS path produce the bad_curie error
        return self._agro if config.ontology_source(prefix) == "agroportal" else self._ols

    # --- single-CURIE methods (route by prefix) ---------------------------

    async def fetch_term(self, curie: str) -> dict:
        return await self._backend_for(curie).fetch_term(curie)

    async def fetch_parents(self, curie: str) -> list[dict]:
        return await self._backend_for(curie).fetch_parents(curie)

    async def fetch_children(self, curie: str) -> list[dict]:
        return await self._backend_for(curie).fetch_children(curie)

    async def fetch_ancestors(self, curie: str) -> list[dict]:
        return await self._backend_for(curie).fetch_ancestors(curie)

    async def fetch_descendants(self, curie: str) -> list[dict]:
        return await self._backend_for(curie).fetch_descendants(curie)

    async def fetch_ontology_version(self, ontology: str) -> str | None:
        if config.ontology_source(ontology) == "agroportal":
            return await self._agro.fetch_ontology_version(ontology)
        return await self._ols.fetch_ontology_version(ontology)

    # --- search (partition by source, merge) ------------------------------

    async def search(
        self,
        query: str,
        ontologies: list[str] | None = None,
        limit: int = 10,
    ) -> list[dict]:
        """Search both backends and merge into one rank-normalized result list.

        ``ontologies=None`` searches all OLS ontologies plus every Crop Ontology.
        A specific list is partitioned by source; a backend with no requested
        ontologies (or AgroPortal with no API key) is skipped. If every queried
        backend errors, the first error list is returned.
        """
        if ontologies is None:
            # Scope the OLS leg to the registry's OLS ontologies — passing None
            # would let OLS search all of OLS4 and return out-of-registry terms.
            ols_arg: list[str] | None = list(config.OLS_ONTOLOGIES)
            call_ols = True
            agro_arg = list(config.CROP_ONTOLOGIES)
            call_agro = self._agro.has_key
        else:
            ols_list = [o for o in ontologies if config.ontology_source(o) == "ols"]
            agro_list = [o for o in ontologies if config.ontology_source(o) == "agroportal"]
            ols_arg, call_ols = ols_list, bool(ols_list)
            agro_arg, call_agro = agro_list, bool(agro_list) and self._agro.has_key

        # The two backends are independent network calls — query them concurrently.
        tasks = []
        if call_ols:
            tasks.append(self._ols.search(query, ols_arg, limit))
        if call_agro:
            tasks.append(self._agro.search(query, agro_arg, limit))

        merged: list[dict] = []
        errors: list[dict] = []
        # A CO-backend error must not sink an otherwise-good OLS search; errors are
        # only surfaced below when nothing else produced results.
        for res in await asyncio.gather(*tasks):
            (errors.extend(res) if _is_error_list(res) else merged.extend(res))

        if not merged:
            return errors[:1] if errors else []

        # Re-rank the merged set by each result's per-source score so the combined
        # list carries one consistent, monotonic 0–1 scale (top hit = 1.0).
        merged.sort(key=lambda r: r.get("score", 0.0), reverse=True)
        merged = merged[:limit]
        total = len(merged)
        for i, item in enumerate(merged):
            item["score"] = rank_score(i, total)
        return merged
