"""suggest_ontology: pure keyword logic mapping a research context to ontologies.

No OLS call and no cache — deterministic local reasoning only.
"""

from ontomcp.core.config import ONTOLOGIES
from ontomcp.core.ols_client import _ONTOLOGY_SLUGS

# Ordered (keywords, ontology codes). First match wins ordering; codes are
# collected in first-seen order across all matching rules. Tuned for plant and
# crop research contexts.
_KEYWORD_RULES: list[tuple[tuple[str, ...], list[str]]] = [
    (("anatomy", "organ", "tissue", "morphology", "root", "leaf", "shoot", "flower"), ["PO"]),
    (("growth stage", "development", "germination", "seedling", "maturity"), ["PO", "PPO"]),
    (("phenology", "flowering time", "senescence", "bud", "season"), ["PPO"]),
    (
        ("trait", "phenotype", "yield", "plant height", "grain", "biomass", "qtl"),
        ["TO", "FLOPO"],
    ),
    (("stress", "drought", "salinity", "heat", "cold", "pathogen", "tolerance"), ["PSO", "PECO"]),
    (
        (
            "treatment",
            "experiment",
            "condition",
            "fertilizer",
            "irrigation",
            "watering",
            "nutrient",
        ),
        ["PECO", "AGRO"],
    ),
    (
        ("agronomy", "agronomic", "farming", "tillage", "cropping", "management", "harvest"),
        ["AGRO"],
    ),
    (("environment", "soil", "climate", "biome", "habitat", "field", "ecosystem"), ["ENVO"]),
    (("population", "germplasm", "accession", "community", "diversity", "panel"), ["PCO"]),
    (("gene", "genome", "expression", "pathway", "function", "annotation", "metabolism"), ["GO"]),
    (("sequence", "variant", "snp", "exon", "transcript", "marker", "locus", "allele"), ["SO"]),
    (("photosynthesis", "respiration", "biosynthesis"), ["GO"]),
]

# A couple of representative terms per ontology, purely illustrative. Every
# registry code has an entry so suggestions always carry examples.
_EXAMPLE_TERMS: dict[str, list[str]] = {
    "PO": ["PO:0025034 (leaf)", "PO:0009005 (root)"],
    "TO": ["TO:0000207 (plant height)", "TO:0000396 (grain yield trait)"],
    "PECO": ["PECO:0007404 (drought exposure)", "PECO:0007087 (natural fertilizer exposure)"],
    "PPO": ["PPO:0007011 (pollen-releasing flower stage)", "PPO:0001032 (unopened flower)"],
    "PSO": ["PSO:0000011 (biotic plant stress)", "PSO:0000012 (abiotic plant stress)"],
    "FLOPO": ["FLOPO:0001221 (flower color)", "FLOPO:0000149 (leaf shape)"],
    "AGRO": ["AGRO:01000015 (tillage)", "AGRO:00000066 (border irrigation process)"],
    "ENVO": ["ENVO:00001998 (soil)", "ENVO:00000077 (agricultural ecosystem)"],
    "PCO": ["PCO:0000005 (population process)", "PCO:0000032 (quantity of organisms)"],
    "GO": ["GO:0015979 (photosynthesis)", "GO:0008152 (metabolic process)"],
    "SO": ["SO:0000704 (gene)", "SO:0000147 (exon)"],
}


def _entry(code: str, rationale: str) -> dict:
    slug = _ONTOLOGY_SLUGS.get(code, code.lower())
    return {
        "ontology": code,
        "rationale": rationale,
        "example_terms": _EXAMPLE_TERMS.get(code, []),
        "ols_url": f"https://www.ebi.ac.uk/ols4/ontologies/{slug}",
    }


def suggest_ontology(context: str) -> tuple[list[dict], bool]:
    """Suggest which ontologies fit a free-text research context.

    Returns ``(results, cache_hit)``. ``cache_hit`` is always False (pure local
    reasoning — no cache is involved). ``results`` is
    ``[{ontology, rationale, example_terms, ols_url}, ...]``, falling back to
    the Plant Ontology + Plant Trait Ontology when no keyword matches.
    """
    text = (context or "").lower()
    ordered: list[str] = []
    for keywords, codes in _KEYWORD_RULES:
        if any(kw in text for kw in keywords):
            for code in codes:
                if code not in ordered:
                    ordered.append(code)

    if not ordered:
        rationale = (
            "No domain keyword matched; defaulting to the general plant anatomy "
            "and trait ontologies."
        )
        return [_entry("PO", rationale), _entry("TO", rationale)], False

    domain_rationale = "Matched the research context to this ontology's domain: "
    return [_entry(code, domain_rationale + ONTOLOGIES[code]["domain"]) for code in ordered], False
