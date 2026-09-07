"""Abaqus Help Documentation RAG for Abaqus MCP Pro.

Provides local Abaqus Help/example search via BM25, TF-IDF, hybrid, and
optional embedding-based scoring. Does not ship or transmit Abaqus Help content;
each user builds their own local index.

Reference: abaqus6.14mcp-main/abaqus-docs-mcp/ (cite/)
"""

from __future__ import annotations

import json
import math
import os
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

DEFAULT_INDEX = Path(
    os.environ.get(
        "ABAQUS_HELP_INDEX",
        str(Path.home() / ".abaqus-mcp-pro" / "abaqus-help-index" / "index.jsonl"),
    )
)
DEFAULT_EMBEDDINGS = Path(
    os.environ.get(
        "ABAQUS_HELP_EMBEDDINGS",
        str(Path.home() / ".abaqus-mcp-pro" / "abaqus-help-index" / "embeddings.jsonl"),
    )
)
EMBED_MODEL = os.environ.get("ABAQUS_HELP_EMBED_MODEL", "BAAI/bge-small-en-v1.5")

# ---------------------------------------------------------------------------
# Tokenizer & stopwords
# ---------------------------------------------------------------------------

STOPWORDS = {
    "the", "and", "for", "with", "that", "this", "from", "are", "you", "your",
    "abaqus", "analysis", "using", "will", "can", "all", "has", "have", "was",
    "were", "been", "section", "more", "information", "see", "use", "used",
    "define", "defined",
}

QUERY_EXPANSIONS = {
    "fpc": ["flexible", "printed", "circuit", "film", "shell", "composite", "bending"],
    "chip": ["chip", "die", "package", "component", "silicon"],
    "flexible": ["flexible", "film", "shell", "membrane"],
    "plate": ["plate", "shell"],
    "bending": ["bending", "bend", "curvature", "static", "riks"],
    "stress": ["stress", "mises", "principal"],
    "static": ["static", "general", "step"],
    "contact": ["contact", "interaction", "surface"],
    "tie": ["tie", "constraint"],
    "constraint": ["constraint", "boundary", "tie"],
    "composite": ["composite", "layered", "shell", "laminate"],
    "shell": ["shell", "s4r", "continuum"],
    "material": ["material", "elastic", "plastic"],
    "mesh": ["mesh", "element", "seed"],
    "modal": ["modal", "frequency", "eigenvalue", "lanczos"],
    "thermal": ["thermal", "temperature", "heat", "conductivity"],
    "dynamic": ["dynamic", "explicit", "implicit", "transient"],
    "fatigue": ["fatigue", "cycle", "endurance", "s-n"],
    "coupled": ["coupled", "temperature-displacement", "thermomechanical"],
    "optimization": ["optimization", "topology", "shape", "sizing", "tosca"],
    "bolt": ["bolt", "pretension", "fastener", "thread"],
    "weld": ["weld", "spot", "seam", "connection"],
    "substructure": ["substructure", "submodel", "global-local"],
    "fracture": ["fracture", "crack", "j-integral", "xfem", "cohesive"],
    "hyperelastic": ["hyperelastic", "rubber", "mooney-rivlin", "ogden", "neo-hookean"],
    "viscoelastic": ["viscoelastic", "creep", "relaxation", "prony"],
    "drucker": ["drucker-prager", "soil", "geotechnical", "mohr-coulomb"],
    "umat": ["umat", "user", "subroutine", "fortran", "vumat"],
    "python": ["python", "scripting", "api", "abaqus scripting"],
}


def tokenize(text: str) -> list[str]:
    tokens = [m.group(0).lower() for m in re.finditer(r"[a-zA-Z][a-zA-Z0-9_+\-]{1,}", text)]
    tokens += [m.group(0).lower() for m in re.finditer(r"\d+(?:\.\d+)?", text)]
    return [token for token in tokens if token not in STOPWORDS]


def expand_query(query: str) -> str:
    expanded = [query]
    query_lower = query.lower()
    for key, values in QUERY_EXPANSIONS.items():
        if key.lower() in query_lower:
            expanded.extend(values)
    return " ".join(expanded)


def record_search_text(record: dict) -> str:
    keywords = record.get("keywords") or []
    if isinstance(keywords, list):
        keywords_text = " ".join(str(item) for item in keywords)
    else:
        keywords_text = str(keywords)
    title = str(record.get("title") or "")
    path = str(record.get("relativePath") or record.get("path") or "")
    sample = str(record.get("textSample") or "")
    kind = str(record.get("kind") or "")
    return " ".join([title] * 4 + [path] * 2 + [keywords_text] * 3 + [kind, sample])


# ---------------------------------------------------------------------------
# Index loading
# ---------------------------------------------------------------------------

def load_records(index_path: Path | None = None) -> list[dict]:
    path = Path(index_path) if index_path else DEFAULT_INDEX
    if not path.exists():
        raise FileNotFoundError(f"Index not found: {path}")
    records: list[dict] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            records.append(json.loads(line))
    return records


def build_corpus(records: list[dict]) -> tuple[list[Counter], dict[str, int], float]:
    term_counts: list[Counter] = []
    document_frequency: dict[str, int] = {}
    total_length = 0
    for record in records:
        counts = Counter(tokenize(record_search_text(record)))
        term_counts.append(counts)
        total_length += sum(counts.values())
        for term in counts:
            document_frequency[term] = document_frequency.get(term, 0) + 1
    avgdl = float(total_length) / float(len(records)) if records else 0.0
    return term_counts, document_frequency, avgdl


# ---------------------------------------------------------------------------
# BM25
# ---------------------------------------------------------------------------

def bm25_score(
    query_terms: list[str],
    counts: Counter,
    df: dict[str, int],
    total_docs: int,
    avgdl: float,
) -> float:
    if not counts or avgdl <= 0:
        return 0.0
    k1 = 1.5
    b = 0.75
    doc_len = float(sum(counts.values()))
    score = 0.0
    for term in query_terms:
        freq = counts.get(term, 0)
        if freq <= 0:
            continue
        term_df = df.get(term, 0)
        idf = math.log(1.0 + (total_docs - term_df + 0.5) / (term_df + 0.5))
        denom = freq + k1 * (1.0 - b + b * doc_len / avgdl)
        score += idf * (freq * (k1 + 1.0)) / denom
    return score


# ---------------------------------------------------------------------------
# TF-IDF
# ---------------------------------------------------------------------------

def tfidf_score(
    query_terms: list[str],
    counts: Counter,
    df: dict[str, int],
    total_docs: int,
) -> float:
    if not counts:
        return 0.0
    doc_len = math.sqrt(sum(value * value for value in counts.values())) or 1.0
    query_counts = Counter(query_terms)
    query_len = math.sqrt(sum(value * value for value in query_counts.values())) or 1.0
    score = 0.0
    for term, qtf in query_counts.items():
        freq = counts.get(term, 0)
        if freq <= 0:
            continue
        idf = math.log((1.0 + total_docs) / (1.0 + df.get(term, 0))) + 1.0
        score += (freq * idf / doc_len) * (qtf * idf / query_len)
    return score


# ---------------------------------------------------------------------------
# Excerpt
# ---------------------------------------------------------------------------

def excerpt(text: str, terms: list[str], limit: int = 420) -> str:
    clean = re.sub(r"\s+", " ", text or "").strip()
    if len(clean) <= limit:
        return clean
    lower = clean.lower()
    positions = [lower.find(term) for term in terms if term and lower.find(term) >= 0]
    start = max(0, min(positions) - 90) if positions else 0
    value = clean[start:start + limit]
    if start > 0:
        value = "..." + value
    if start + limit < len(clean):
        value += "..."
    return value


# ---------------------------------------------------------------------------
# Lexical search (BM25 / TF-IDF / hybrid)
# ---------------------------------------------------------------------------

def search_lexical(
    index_path: Path,
    query: str,
    limit: int = 5,
    method: str = "bm25",
) -> list[dict[str, Any]]:
    records = load_records(index_path)
    if not records:
        return []
    expanded_query = expand_query(query)
    query_terms = tokenize(expanded_query)
    if not query_terms:
        return []
    term_counts, df, avgdl = build_corpus(records)
    total_docs = len(records)

    scored = []
    for record, counts in zip(records, term_counts):
        bm25 = bm25_score(query_terms, counts, df, total_docs, avgdl)
        tfidf = tfidf_score(query_terms, counts, df, total_docs)
        if method == "tfidf":
            score = tfidf
        elif method == "hybrid":
            score = bm25 + 2.0 * tfidf
        else:
            score = bm25
        if score <= 0:
            continue
        sample = str(record.get("textSample") or "")
        result = {
            "score": round(score, 6),
            "method": method,
            "kind": record.get("kind"),
            "title": record.get("title"),
            "relativePath": record.get("relativePath"),
            "path": record.get("path"),
            "keywords": record.get("keywords") or [],
            "excerpt": excerpt(sample, query_terms),
        }
        scored.append(result)
    scored.sort(key=lambda item: item["score"], reverse=True)
    return scored[:limit]


# ---------------------------------------------------------------------------
# Embedding search (optional, requires sentence-transformers)
# ---------------------------------------------------------------------------

_MODEL_CACHE: dict = {}


def _load_sentence_transformer(model_name: str, local_files_only: bool = True):
    cache_key = (model_name, local_files_only)
    if cache_key in _MODEL_CACHE:
        return _MODEL_CACHE[cache_key]
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError as exc:
        raise RuntimeError(
            "sentence-transformers is not installed. "
            "Install it: pip install sentence-transformers"
        ) from exc

    kwargs = {}
    if local_files_only:
        kwargs["local_files_only"] = True
    try:
        model = SentenceTransformer(model_name, **kwargs)
    except TypeError:
        model = SentenceTransformer(model_name)
    _MODEL_CACHE[cache_key] = model
    return model


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = 0.0
    norm_a = 0.0
    norm_b = 0.0
    for av, bv in zip(a, b):
        dot += av * bv
        norm_a += av * av
        norm_b += bv * bv
    if norm_a <= 0 or norm_b <= 0:
        return 0.0
    return dot / ((norm_a ** 0.5) * (norm_b ** 0.5))


def search_embeddings(
    embeddings_path: Path,
    query: str,
    model_name: str = "BAAI/bge-small-en-v1.5",
    limit: int = 5,
    local_files_only: bool = True,
) -> list[dict[str, Any]]:
    if not embeddings_path.exists():
        raise FileNotFoundError(
            f"Embeddings not found: {embeddings_path}. "
            "Run build-abaqus-help-embeddings first."
        )
    model = _load_sentence_transformer(model_name, local_files_only)
    query_vector = [float(value) for value in model.encode(query, normalize_embeddings=True)]

    scored = []
    with embeddings_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            score = _cosine_similarity(query_vector, record.get("embedding") or [])
            if score > 0:
                scored.append((score, record))
    scored.sort(key=lambda item: item[0], reverse=True)

    results = []
    for score, record in scored[:max(1, limit)]:
        sample = str(record.get("textSample") or "")
        if len(sample) > 420:
            sample = sample[:420] + "..."
        results.append({
            "score": round(score, 6),
            "method": "embedding",
            "model": record.get("model"),
            "kind": record.get("kind"),
            "title": record.get("title"),
            "relativePath": record.get("relativePath"),
            "path": record.get("path"),
            "keywords": record.get("keywords") or [],
            "excerpt": sample,
        })
    return results


# ---------------------------------------------------------------------------
# MCP Tool wrappers
# ---------------------------------------------------------------------------


async def search_abaqus_help(
    query: str,
    limit: int = 5,
    method: str = "bm25",
) -> str:
    """Search local Abaqus Help/example index.

    Supports BM25, TF-IDF, hybrid, and embedding scoring.
    Requires a pre-built local index (see index-abaqus-help.ps1).

    Args:
        query: Search query string (e.g. "cantilever static C3D8R bending stress").
        limit: Maximum number of results (1-20).
        method: Scoring method: "bm25", "tfidf", "hybrid", or "embedding"/"semantic".
    """
    limit = max(1, min(int(limit), 20))
    method = str(method).lower().strip()

    if method in ("embedding", "semantic"):
        try:
            results = search_embeddings(
                DEFAULT_EMBEDDINGS,
                query,
                model_name=EMBED_MODEL,
                limit=limit,
                local_files_only=True,
            )
            return json.dumps(results, indent=2, ensure_ascii=False, default=str)
        except Exception as exc:
            return json.dumps({
                "error": str(exc),
                "hint": (
                    "Embedding search unavailable. Run setup-abaqus-help-embeddings.ps1 "
                    "to build embeddings, or use method='hybrid' for lexical search."
                ),
            }, indent=2)

    if method not in ("bm25", "tfidf", "hybrid"):
        method = "bm25"

    try:
        results = search_lexical(DEFAULT_INDEX, query, limit=limit, method=method)
        return json.dumps(results, indent=2, ensure_ascii=False, default=str)
    except FileNotFoundError as exc:
        return json.dumps({
            "error": str(exc),
            "hint": (
                "No local Abaqus Help index found. Build one with: "
                "scripts/index-abaqus-help.ps1"
            ),
        }, indent=2)


async def get_abaqus_doc_entry(path_or_id: str) -> str:
    """Return one indexed Abaqus Help/example entry by id, path, relative path, or title.

    Args:
        path_or_id: Document identifier, path, relative path, or title to look up.
    """
    needle = str(path_or_id).strip().lower()
    if not needle:
        return json.dumps({"error": "path_or_id is required"}, indent=2)

    try:
        records = load_records()
    except FileNotFoundError as exc:
        return json.dumps({"error": str(exc)}, indent=2)

    for record in records:
        candidates = [
            str(record.get("id") or ""),
            str(record.get("path") or ""),
            str(record.get("relativePath") or ""),
            str(record.get("title") or ""),
        ]
        if any(value.lower() == needle for value in candidates):
            return json.dumps(record, indent=2, ensure_ascii=False, default=str)

    matches = []
    for record in records:
        haystack = " ".join([
            str(record.get("path") or ""),
            str(record.get("relativePath") or ""),
            str(record.get("title") or ""),
        ]).lower()
        if needle in haystack:
            matches.append(record)
        if len(matches) >= 5:
            break

    if matches:
        return json.dumps({"matches": matches}, indent=2, ensure_ascii=False, default=str)
    return json.dumps({"error": "No matching indexed entry", "query": path_or_id}, indent=2)


async def suggest_abaqus_pattern(description: str, limit: int = 5, method: str = "hybrid") -> str:
    """Suggest Abaqus modeling patterns from local docs/examples for a simulation description.

    Args:
        description: Natural language description of the simulation task.
        limit: Maximum number of reference results (1-10).
        method: Scoring method: "bm25", "tfidf", "hybrid", or "embedding"/"semantic".
    """
    description_lower = str(description).lower()
    hints: list[str] = []

    if any(term in description_lower for term in ("bend", "bending", "curvature")):
        hints.append(
            "Consider static general step, shell/solid choice by thickness, "
            "prescribed displacement/rotation or curvature boundary conditions."
        )
    if any(term in description_lower for term in ("fpc", "flexible", "composite", "layer")):
        hints.append(
            "Check shell/composite/layered modeling patterns and validate "
            "tie constraints between components and substrate."
        )
    if any(term in description_lower for term in ("chip", "component", "package")):
        hints.append(
            "Use simplified component solids for early screening; "
            "tie or cohesive/contact interfaces depending on fidelity."
        )
    if any(term in description_lower for term in ("contact", "tie", "cohesive")):
        hints.append(
            "Search tie constraints and surface contact definitions "
            "before choosing interaction behavior."
        )
    if any(term in description_lower for term in ("thermal", "temperature", "cte")):
        hints.append(
            "Include thermal expansion and sequential/fully coupled "
            "thermal-stress only when temperature loading matters."
        )
    if any(term in description_lower for term in ("modal", "frequency", "vibration", "eigenvalue")):
        hints.append(
            "Ensure density is defined for mass matrix. "
            "No loads needed for eigenvalue extraction."
        )
    if any(term in description_lower for term in ("dynamic", "impact", "crash", "drop")):
        hints.append(
            "Check event duration: < 10ms with impact -> explicit; "
            "> 100ms without severe nonlinearity -> implicit."
        )
    if any(term in description_lower for term in ("fatigue", "cycle", "endurance")):
        hints.append(
            "Abaqus has limited native fatigue. Run structural analysis first, "
            "then apply S-N or e-N criteria externally."
        )
    if any(term in description_lower for term in ("optimization", "topology", "topology optimization")):
        hints.append(
            "Requires Tosca license (not Learning Edition). "
            "Define design space, frozen regions, and manufacturing constraints."
        )

    if not hints:
        hints.append(
            "Start with a small linear static smoke test, "
            "then increase geometric/material fidelity."
        )

    limited = max(1, min(int(limit), 10))
    method = str(method).lower().strip()
    reference_query = " ".join([description] + hints)

    if method in ("embedding", "semantic"):
        try:
            results = search_embeddings(
                DEFAULT_EMBEDDINGS,
                reference_query,
                model_name=EMBED_MODEL,
                limit=limited,
                local_files_only=True,
            )
        except Exception:
            results = [{
                "error": "Embedding search unavailable; falling back to hybrid lexical search.",
            }]
            try:
                results.extend(search_lexical(DEFAULT_INDEX, reference_query, limit=limited, method="hybrid"))
            except FileNotFoundError:
                pass
    else:
        try:
            results = search_lexical(DEFAULT_INDEX, reference_query, limit=limited, method=method)
        except FileNotFoundError:
            results = [{"error": "No local Abaqus Help index found."}]

    return json.dumps({
        "description": description,
        "method": method,
        "patternHints": hints,
        "localReferences": results,
    }, indent=2, ensure_ascii=False, default=str)


async def get_abaqus_docs_status() -> str:
    """Return local Abaqus docs index status."""
    exists = DEFAULT_INDEX.exists()
    count = 0
    if exists:
        with DEFAULT_INDEX.open("r", encoding="utf-8") as handle:
            count = sum(1 for line in handle if line.strip())
    return json.dumps({
        "indexPath": str(DEFAULT_INDEX),
        "exists": exists,
        "entries": count,
        "embeddingsPath": str(DEFAULT_EMBEDDINGS),
        "embeddingsExists": DEFAULT_EMBEDDINGS.exists(),
        "embeddingModel": EMBED_MODEL,
    }, indent=2)
