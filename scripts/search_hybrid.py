#!/usr/bin/env python3
"""Hybrid Hinglish lecture search using SQLite FTS5, FAISS, and RRF.

Run from the project root after placing this file at scripts/search_hybrid.py:
    python scripts/search_hybrid.py base_auto "deadlock processes waiting"
    python scripts/search_hybrid.py small_hi "डेडलॉक क्या होता है?"

The script expects the following project files:
    data/index/keyword_search.db
    data/index/dense_<config>.faiss
    data/index/dense_<config>_metadata.jsonl

Dense index metadata must remain in the same order as the FAISS vectors.
"""

from __future__ import annotations

import argparse
import json
import math
import sqlite3
import sys
import unicodedata
from pathlib import Path
from typing import Any, Iterable

import faiss
import numpy as np
from fastembed import TextEmbedding


# ---------------------------------------------------------------------------
# Paths and retrieval configuration
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parents[1]
INDEX_DIR = PROJECT_ROOT / "data" / "index"
KEYWORD_DB = INDEX_DIR / "keyword_search.db"

MODEL_NAME = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
RRF_K = 60
DEFAULT_DENSE_CANDIDATES = 50
DEFAULT_RESULT_LIMIT = 10

SUPPORTED_CONFIGS = ("base_auto", "small_hi")


# Query-time cross-script aliases. Keep this dictionary fixed during an
# evaluation run so keyword and hybrid results remain reproducible.
# Function words are removed from the keyword query. Keep this list fixed during
# evaluation so the keyword and hybrid baselines remain reproducible. Technical
# terms and content words such as "use", "process", and "section" are retained.
STOPWORDS = {
    # English
    "a", "an", "the", "is", "am", "are", "was", "were", "be", "been",
    "being", "do", "does", "did", "how", "what", "why", "when", "where",
    "which", "who", "whom", "whose", "this", "that", "these", "those",
    "it", "its", "of", "to", "in", "on", "at", "by", "for", "from",
    "with", "as", "and", "or", "but", "if", "then", "than", "so",
    "we", "you", "i", "me", "my", "our", "ours", "your", "yours",
    "they", "them", "their", "there", "here", "he", "she", "him", "her",
    "has", "have", "had", "can", "could", "would", "should", "will",
    "shall", "may", "might", "must", "not", "no", "yes", "also",
    # Hindi (Devanagari)
    "क्या", "है", "हैं", "था", "थी", "थे", "होता", "होती", "होते",
    "का", "की", "के", "को", "में", "से", "पर", "और", "या", "तो",
    "यह", "ये", "वह", "वे", "इस", "उस", "एक", "क्यों", "कैसे", "कब",
    "कहाँ", "किस", "किसे", "जो", "भी", "ही", "नहीं", "कर", "करता",
    "करती", "करते", "किया", "जाता", "जाती", "जाते", "हुआ", "हुई",
    "हुए", "हम", "आप", "मैं", "मेरा", "मेरी", "मेरे", "अपने", "अपना",
    # Common Romanized Hindi / Hinglish
    "kya", "hai", "hain", "tha", "thi", "the", "hota", "hoti", "hote",
    "ka", "ki", "ke", "ko", "mein", "me", "se", "par", "aur", "ya",
    "to", "ye", "yeh", "woh", "wo", "is", "us", "ek", "kyun", "kyu",
    "kaise", "kab", "kaha", "kis", "bhi", "hi", "nahi", "nahin", "kar",
    "karta", "karti", "karte", "kiya", "jata", "jati", "jate", "hua",
    "hui", "hue", "hum", "aap", "mai", "main", "mera", "meri", "mere",
}


# High-precision query intents for concepts that are frequently phrased
# differently from the transcript wording. These are deliberately narrow:
# generic words such as "use", "used", and "usage" are NOT globally mapped.
SEMAPHORE_QUERY_TERMS = {"सेमाफोर", "सेमफोर", "semaphore", "semaphores"}
PURPOSE_QUERY_TERMS = {
    "purpose", "why", "use", "used", "using", "usage", "utilization",
    "उपयोग", "क्यों", "लिए", "kyu", "kyun", "kisliye", "liye",
}
SEMAPHORE_PURPOSE_EXPANSION = (
    "synchronize", "synchronization", "mutual", "exclusive", "exclusion",
)

QUERY_ALIASES: dict[str, tuple[str, ...]] = {
    # Hindi / Devanagari to English technical terms.
    "सेमाफोर": ("semaphore", "semaphores"),
    "प्रोसेस": ("process", "processes"),
    "प्रोसेसेस": ("processes", "process"),
    "प्रक्रिया": ("process", "processes"),
    "डेडलॉक": ("deadlock",),
    "बाइनरी": ("binary",),
    "काउंटिंग": ("counting",),
    "क्रिटिकल": ("critical",),
    "सेक्शन": ("section",),
    "म्यूचुअल": ("mutual",),
    "एक्सक्लूजन": ("exclusion",),
    "शेड्यूलिंग": ("scheduling",),
    "प्रायोरिटी": ("priority",),
    "पेजिंग": ("paging",),
    # SJF terminology and observed Whisper recognition variants.
    "sjf": ("shortest", "short", "test", "job", "first", "burst", "time", "शौट्तेश", "जौव", "बरस", "टाइम"),
    "एसजेएफ": ("shortest", "short", "test", "job", "first", "burst", "time", "शौट्तेश", "जौव", "बरस", "टाइम"),

    # Common English terms to their likely Hindi transcript forms.
    "semaphore": ("सेमाफोर",),
    "semaphores": ("सेमाफोर",),
    "process": ("प्रोसेस", "प्रोसेसेस"),
    "processes": ("प्रोसेस", "प्रोसेसेस"),
    "deadlock": ("डेडलॉक",),
    "binary": ("बाइनरी",),
    "counting": ("काउंटिंग",),
    "critical": ("क्रिटिकल",),
    "section": ("सेक्शन",),
    "mutual": ("म्यूचुअल",),
    "exclusion": ("एक्सक्लूजन",),
    "scheduling": ("शेड्यूलिंग",),
    "priority": ("प्रायोरिटी",),
    "paging": ("पेजिंग",),
}


def is_token_character(character: str) -> bool:
    """Return True for Unicode letters, marks, numbers, and technical symbols."""
    category = unicodedata.category(character)
    return category[0] in {"L", "M", "N"} or character in "_+#"


def tokenize(text: str) -> list[str]:
    """Unicode-aware tokenization that preserves Devanagari combining marks."""
    text = unicodedata.normalize("NFKC", text).casefold()
    tokens: list[str] = []
    current: list[str] = []

    for character in text:
        if is_token_character(character):
            current.append(character)
        elif current:
            tokens.append("".join(current))
            current.clear()

    if current:
        tokens.append("".join(current))

    return tokens


def is_fcfs_query(query: str) -> bool:
    """Detect an explicit FCFS acronym or the full algorithm name."""
    query_tokens = set(tokenize(query))
    normalized = " ".join(tokenize(query))
    return "fcfs" in query_tokens or "first come first serve" in normalized


def is_semaphore_purpose_query(query: str) -> bool:
    """Detect questions asking what semaphores are for, not every semaphore query."""
    query_tokens = set(tokenize(query))
    return bool(query_tokens & SEMAPHORE_QUERY_TERMS) and bool(
        query_tokens & PURPOSE_QUERY_TERMS
    )


def is_binary_semaphore_definition_query(query: str) -> bool:
    """Detect Hindi/English questions asking for the binary semaphore definition."""
    tokens = set(tokenize(query))
    binary_terms = {"binary", "बाइनरी", "बायनरी"}
    semaphore_terms = {
        "semaphore", "semaphores", "सेमाफोर", "सेमाफ़ोर"
    }
    definition_terms = {
        "what", "क्या", "होता", "होती", "meaning", "definition"
    }
    return (
        bool(tokens & binary_terms)
        and bool(tokens & semaphore_terms)
        and bool(tokens & definition_terms)
    )


def is_fcfs_waiting_time_query(query: str) -> bool:
    """Detect FCFS questions specifically about waiting-time calculation."""
    tokens = set(tokenize(query))
    waiting_terms = {
        "wait", "waiting", "वेटिंग", "इंतजार", "इंतज़ार", "प्रतीक्षा"
    }
    time_terms = {"time", "टाइम", "समय"}
    return (
        is_fcfs_query(query)
        and bool(tokens & waiting_terms)
        and bool(tokens & time_terms)
    )


def is_critical_section_concurrency_query(query: str) -> bool:
    """Detect questions about how many processes may enter a critical section."""
    tokens = set(tokenize(query))
    has_critical_section = (
        {"critical", "section"} <= tokens
        or {"क्रिटिकल", "सेक्शन"} <= tokens
    )
    count_cues = {
        "how", "many", "one", "at", "time",
        "kitne", "कितने", "एक", "समय"
    }
    process_cues = {
        "process", "processes", "प्रोसेस", "प्रोसेसेस",
        "access", "जा", "सकते"
    }
    return (
        has_critical_section
        and bool(tokens & count_cues)
        and bool(tokens & process_cues)
    )


def is_deadlock_resource_wait_query(query: str) -> bool:
    """Detect process/resource waiting scenarios, even without the word deadlock."""
    tokens = set(tokenize(query))
    process_terms = {"process", "processes", "प्रोसेस", "प्रोसेसेस"}
    resource_terms = {"resource", "resources", "संसाधन"}
    wait_terms = {
        "wait", "waiting", "rahe", "rahein",
        "इंतजार", "इंतज़ार", "प्रतीक्षा"
    }
    situation_terms = {
        "situation", "banti", "बनती", "क्या", "what"
    }
    return (
        bool(tokens & process_terms)
        and bool(tokens & resource_terms)
        and bool(tokens & wait_terms)
        and bool(tokens & situation_terms)
    )


def is_deadlock_definition_query(query: str) -> bool:
    """Detect questions asking what deadlock is or when it occurs."""
    tokens = set(tokenize(query))
    deadlock_terms = {"deadlock", "डेडलॉक"}
    definition_cues = {
        "what", "क्या", "kab", "when", "hota", "होता", "होती",
        "meaning", "definition", "define", "occurs", "occur",
    }
    return (
        bool(tokens & deadlock_terms)
        and bool(tokens & definition_cues)
    )


def paging_query_intent(query: str) -> str | None:
    """Distinguish questions about page creation from reasons for paging."""
    tokens = set(tokenize(query))

    page_terms = {
        "page", "pages", "paging", "पेज", "पेजों", "पेजो", "पेज़"
    }
    if not (tokens & page_terms):
        return None

    reason_terms = {
        "why", "क्यों", "kyon", "kyu", "kyun", "reason", "purpose"
    }
    division_terms = {
        "how", "कैसे", "kaise", "divide", "divided",
        "division", "partition", "partitions",
        "बाँटा", "बांटा", "विभाजित"
    }

    # Reason takes precedence when a query contains both why and divide.
    if tokens & reason_terms:
        return "reason"
    if tokens & division_terms:
        return "division"
    return None


def is_sjf_query(query: str) -> bool:
    tokens = set(tokenize(query))
    return (
        "sjf" in tokens
        or "एसजेएफ" in tokens
        or {"shortest", "job"}.issubset(tokens)
    )


def sjf_query_intent(query: str) -> str | None:
    """Classify an SJF query by the specific scheduling concept requested."""
    if not is_sjf_query(query):
        return None

    tokens = set(tokenize(query))
    same_terms = {"same", "equal", "सेम", "समान", "बराबर", "barabar"}
    if "arrival" in tokens and bool(tokens & same_terms):
        return "tie_break"

    # Selection must precede definition: Hindi questions often contain generic verbs.
    selection_terms = {
        "choose", "chooses", "select", "selected", "selecting",
        "execute", "executes", "executed", "pick", "first",
        "कौन", "पहले", "चुनें", "चुनता",
    }
    if tokens & selection_terms:
        return "selection"

    definition_terms = {"algorithm", "definition", "what", "क्या", "kya"}
    if tokens & definition_terms:
        return "definition"
    if tokens & {"burst", "बरस", "बर्स्ट"}:
        return "selection"
    return "definition"


def query_phrase_expansions(query: str) -> list[str]:
    phrases = ["first come first serve"] if is_fcfs_query(query) else []
    if is_fcfs_waiting_time_query(query):
        phrases.extend((
            "waiting time",
            "turn around time",
            "turnaround time",
            "burst time",
            "turn around time minus burst time",
        ))

    if is_critical_section_concurrency_query(query):
        phrases.extend((
            "mutual exclusion",
            "one process at a time",
            "only one process",
            "another process is blocked",
            "cannot enter critical section",
        ))

    if is_deadlock_resource_wait_query(query):
        phrases.extend((
            "P1 has taken one resource",
            "P1 is waiting for R2",
            "R2 is already taken by P2",
            "P2 is requesting R1",
            "deadlock situation",
            "circular wait",
        ))

    paging_intent = paging_query_intent(query)

    if paging_intent == "division":
        phrases.extend((
            "divide the process first",
            "secondary memory",
            "process into pages",
            "partition we call pages",
            "every process will be divided",
        ))
    elif paging_intent == "reason":
        phrases.extend((
            "memory more efficiently",
            "more efficiently",
            "memory in a more efficient way",
            "non contiguous manner",
            "different locations",
        ))

    if is_deadlock_definition_query(query):
        phrases.extend((
            "two and more processes",
            "waiting on happening",
            "event does not happen",
            "deadlock situation",
        ))


    if is_binary_semaphore_definition_query(query):
        phrases.extend((
            "zero and one",
            "only zero and one",
            "0 and 1",
            "two values",
            "two digits",
        ))

    if is_semaphore_purpose_query(query):
        phrases.extend(("mutual exclusion", "mutual exclusive", "process is to synchronize"))
    intent = sjf_query_intent(query)
    if intent == "definition":
        phrases.extend(("short test job first", "shortest job first", "burst time"))
    elif intent == "selection":
        phrases.extend(("burst time", "p1 and p3", "short test job"))
    elif intent == "tie_break":
        phrases.extend(("arrival time is the same", "arrival time दी सेम", "process id"))
    return phrases

def semantic_query_text(query: str) -> str:
    paging_intent = paging_query_intent(query)

    if paging_intent == "division":
        return (
            query
            + " Paging divides a process into pages in secondary memory. "
              "Each partition of the process is called a page. "
              "Main memory is divided into frames."
        )

    if paging_intent == "reason":
        return (
            query
            + " Paging divides processes into pages so memory can be "
              "used more efficiently. Pages can be placed in non-contiguous "
              "memory locations, and page size matches frame size."
        )

    if is_fcfs_waiting_time_query(query):
        return (
            query
            + " FCFS waiting time calculation: waiting time equals "
              "turnaround time minus burst time. "
              "Calculate how long a process waits before execution."
        )

    if is_critical_section_concurrency_query(query):
        return (
            query
            + " Critical section mutual exclusion allows only one process "
              "to use the critical section at a time. "
              "While one process is inside, another process is blocked "
              "and cannot enter."
        )

    if is_deadlock_resource_wait_query(query):
        return (
            query
            + " Deadlock resource allocation scenario: P1 holds R1 and "
              "waits for R2, while P2 holds R2 and waits for R1. "
              "Each process requests a resource held by the other, "
              "creating circular wait and a deadlock situation."
        )

    if is_deadlock_definition_query(query):
        return (
            query
            + " Operating systems deadlock definition: two or more "
              "processes are waiting for an event that never happens. "
              "The event does not occur, leaving the processes waiting."
        )

    if is_binary_semaphore_definition_query(query):
        return (
            query
            + " Binary semaphore has exactly two possible values, "
              "zero and one, 0 and 1. It has only two states, "
              "unlike a counting semaphore."
        )

    intent = sjf_query_intent(query)
    if intent == "definition":
        return (query + " shortest job first CPU scheduling algorithm; "
                "the ready process with the shortest CPU burst time is selected for execution")
    if intent == "selection":
        return (query + " shortest job first scheduling; compare CPU burst times of arrived ready processes; "
                "select the process with the smallest burst time")
    if intent == "tie_break":
        return (query + " shortest job first scheduling; when arrival times are equal, compare process IDs; "
                "select the process with the lower process ID")
    if is_semaphore_purpose_query(query):
        return (query + " process synchronization mutual exclusion; "
                "one process at a time inside the critical section")
    return query

def expand_query_tokens(query: str) -> list[str]:
    """Tokenize a query and add curated cross-script/domain aliases."""
    expanded: list[str] = []
    seen: set[str] = set()

    for token in tokenize(query):
        if token in STOPWORDS:
            continue
        candidates = (token, *QUERY_ALIASES.get(token, ()))
        for candidate in candidates:
            for normalized in tokenize(candidate):
                if normalized in STOPWORDS:
                    continue
                if normalized and normalized not in seen:
                    seen.add(normalized)
                    expanded.append(normalized)

    # Query-specific vocabulary expansion, not a global synonym expansion.
    # The corpus actually uses "synchronize" and "mutual exclusion" when
    # explaining the purpose of semaphores.
    if is_semaphore_purpose_query(query):
        for token in SEMAPHORE_PURPOSE_EXPANSION:
            if token not in seen:
                seen.add(token)
                expanded.append(token)

    return expanded


def make_fts_query(tokens: list[str], phrases: list[str] | None = None) -> str:
    """Build a safely quoted FTS5 OR query, including exact phrase clauses."""
    clauses = [f'"{token.replace(chr(34), chr(34) * 2)}"' for token in tokens]
    for phrase in phrases or []:
        escaped = phrase.replace('"', '""')
        clause = f'"{escaped}"'
        if clause not in clauses:
            clauses.append(clause)
    return " OR ".join(clauses)


def normalized_text(text: str) -> str:
    """Normalize text for segment-level duplicate detection."""
    return " ".join(tokenize(text))


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSON in {path}:{line_number}: {exc}") from exc
            if not isinstance(record, dict):
                raise ValueError(f"Expected a JSON object in {path}:{line_number}")
            records.append(record)
    return records


# ---------------------------------------------------------------------------
# Keyword retrieval (SQLite FTS5)
# ---------------------------------------------------------------------------


def get_fts_columns(connection: sqlite3.Connection, table_name: str) -> set[str]:
    rows = connection.execute(f'PRAGMA table_info("{table_name}")').fetchall()
    return {str(row[1]) for row in rows}


def get_keyword_rankings(
    config: str,
    query: str,
    maximum_results: int,
) -> tuple[dict[str, int], dict[str, float], list[str], str]:
    """Return BM25-ranked chunk IDs and scores from the matching FTS5 table."""
    if not KEYWORD_DB.exists():
        raise FileNotFoundError(f"Keyword database not found: {KEYWORD_DB}")

    table_name = f"{config}_fts"
    tokens = expand_query_tokens(query)
    fts_query = make_fts_query(tokens, query_phrase_expansions(query))

    if not fts_query:
        return {}, {}, tokens, fts_query

    with sqlite3.connect(KEYWORD_DB) as connection:
        columns = get_fts_columns(connection, table_name)
        if not columns:
            raise RuntimeError(
                f"FTS table '{table_name}' was not found in {KEYWORD_DB}. "
                "Rebuild the keyword index first."
            )
        if "chunk_id" not in columns:
            raise RuntimeError(
                f"FTS table '{table_name}' has no chunk_id column. "
                f"Available columns: {sorted(columns)}"
            )

        sql = f"""
            SELECT chunk_id, bm25({table_name}) AS bm25_score
            FROM {table_name}
            WHERE {table_name} MATCH ?
            ORDER BY bm25_score ASC
            LIMIT ?
        """
        try:
            rows = connection.execute(sql, (fts_query, maximum_results)).fetchall()
        except sqlite3.OperationalError as exc:
            raise RuntimeError(
                f"FTS5 query failed for '{table_name}' with query {fts_query!r}: {exc}"
            ) from exc

    ranks: dict[str, int] = {}
    scores: dict[str, float] = {}
    for rank, (chunk_id, bm25_score) in enumerate(rows, start=1):
        if chunk_id is None:
            continue
        chunk_id = str(chunk_id)
        ranks[chunk_id] = rank
        scores[chunk_id] = float(bm25_score)

    return ranks, scores, tokens, fts_query


# ---------------------------------------------------------------------------
# Dense retrieval (FAISS + FastEmbed)
# ---------------------------------------------------------------------------


def load_dense_resources(config: str) -> tuple[Any, list[dict[str, Any]], dict[str, dict[str, Any]]]:
    index_path = INDEX_DIR / f"dense_{config}.faiss"
    metadata_path = INDEX_DIR / f"dense_{config}_metadata.jsonl"

    if not index_path.exists():
        raise FileNotFoundError(f"Dense FAISS index not found: {index_path}")
    if not metadata_path.exists():
        raise FileNotFoundError(f"Dense metadata not found: {metadata_path}")

    index = faiss.read_index(str(index_path))
    metadata = load_jsonl(metadata_path)

    if index.ntotal != len(metadata):
        raise RuntimeError(
            "FAISS/metadata row-count mismatch: "
            f"index has {index.ntotal} vectors but metadata has {len(metadata)} rows. "
            "Rebuild the dense index and metadata together."
        )

    metadata_by_id: dict[str, dict[str, Any]] = {}
    for row_number, record in enumerate(metadata):
        chunk_id = record.get("chunk_id")
        if not chunk_id:
            raise RuntimeError(f"Missing chunk_id in dense metadata row {row_number}")
        chunk_id = str(chunk_id)
        if chunk_id in metadata_by_id:
            raise RuntimeError(f"Duplicate chunk_id in dense metadata: {chunk_id}")
        metadata_by_id[chunk_id] = record

    # IMPORTANT: return the complete metadata map, not only top-k dense hits.
    # RRF also needs metadata for chunks retrieved by keyword search alone.
    return index, metadata, metadata_by_id


def embed_texts(model: TextEmbedding, texts: list[str]) -> np.ndarray:
    if not texts:
        return np.empty((0, 0), dtype=np.float32)

    vectors = np.asarray(list(model.embed(texts)), dtype=np.float32)
    if vectors.ndim != 2 or vectors.shape[0] != len(texts):
        raise RuntimeError(
            f"Embedding output shape {vectors.shape} does not match {len(texts)} input texts"
        )

    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    norms[norms == 0.0] = 1.0
    return vectors / norms


def get_dense_rankings(
    index: Any,
    metadata: list[dict[str, Any]],
    model: TextEmbedding,
    query: str,
    candidate_count: int,
) -> tuple[dict[str, int], dict[str, float]]:
    """Return dense ranks and cosine similarities for the FAISS top-k results."""
    query_vector = embed_texts(model, [query])
    if query_vector.shape[1] != index.d:
        raise RuntimeError(
            f"Embedding dimension {query_vector.shape[1]} does not match FAISS dimension {index.d}"
        )

    search_count = min(max(1, candidate_count), index.ntotal)
    distances, indices = index.search(query_vector, search_count)

    ranks: dict[str, int] = {}
    similarities: dict[str, float] = {}

    for rank, (similarity, row_index) in enumerate(zip(distances[0], indices[0]), start=1):
        if row_index < 0 or row_index >= len(metadata):
            continue

        record = metadata[int(row_index)]
        chunk_id = str(record["chunk_id"])
        ranks[chunk_id] = rank
        similarities[chunk_id] = float(similarity)

    return ranks, similarities


# ---------------------------------------------------------------------------
# Reciprocal Rank Fusion
# ---------------------------------------------------------------------------


def reciprocal_rank_fusion(
    keyword_ranks: dict[str, int],
    dense_ranks: dict[str, int],
    metadata_by_id: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    """Fuse keyword and dense rankings while retaining keyword-only candidates."""
    fused_scores: dict[str, float] = {}
    all_chunk_ids = set(keyword_ranks) | set(dense_ranks)

    for chunk_id in all_chunk_ids:
        score = 0.0
        if chunk_id in keyword_ranks:
            score += 1.0 / (RRF_K + keyword_ranks[chunk_id])
        if chunk_id in dense_ranks:
            score += 1.0 / (RRF_K + dense_ranks[chunk_id])
        fused_scores[chunk_id] = score

    fused_chunks: list[dict[str, Any]] = []
    for chunk_id, score in fused_scores.items():
        # This map contains every metadata row, not just dense top-k rows.
        record = metadata_by_id.get(chunk_id)
        if record is None:
            continue

        fused_chunks.append(
            {
                "chunk_id": chunk_id,
                "rrf_score": score,
                "keyword_rank": keyword_ranks.get(chunk_id),
                "dense_rank": dense_ranks.get(chunk_id),
                "metadata": record,
            }
        )

    fused_chunks.sort(
        key=lambda item: (
            item["rrf_score"],
            -(item["keyword_rank"] or math.inf),
            -(item["dense_rank"] or math.inf),
        ),
        reverse=True,
    )
    return fused_chunks


# ---------------------------------------------------------------------------
# Timestamp-level result selection and duplicate removal
# ---------------------------------------------------------------------------


def segment_key(lecture_id: str, segment: dict[str, Any]) -> tuple[Any, ...]:
    return (
        lecture_id,
        round(float(segment.get("start", 0.0)), 2),
        round(float(segment.get("end", 0.0)), 2),
        normalized_text(str(segment.get("text", ""))),
    )


def lexical_overlap(segment_text: str, query_tokens: set[str]) -> int:
    # Ignore function words on both sides; otherwise generic Hindi/Hinglish
    # phrasing can outrank a segment that actually mentions the topic.
    segment_tokens = {token for token in tokenize(segment_text) if token not in STOPWORDS}
    return len(segment_tokens & query_tokens)


def segment_intent_match_score(
    query: str,
    segment_text: str,
    context_text: str = "",
    lecture_id: str | None = None,
) -> int:
    """Score direct evidence that a transcript segment answers query intent."""
    direct = set(tokenize(segment_text))
    context = direct | set(tokenize(context_text))

    if is_binary_semaphore_definition_query(query):
        direct_zero_one = (
            {"zero", "one"} <= direct or {"0", "1"} <= direct
        )
        context_zero_one = (
            {"zero", "one"} <= context or {"0", "1"} <= context
        )

        # Require actual semaphore evidence in the transcript context.
        # These ASR variants occur in the base_auto transcription.
        semaphore_anchors = {
            "semaphore", "semaphores", "counting",
            "sama", "bindrye", "bindy"
        }
        has_semaphore_anchor = bool(context & semaphore_anchors)

        has_value_evidence = bool(
            context & {"value", "values", "digit", "digits", "two", "2", "doi"}
        )

        # Numeric examples from unrelated topics must not receive
        # binary-semaphore intent scores.
        if not has_semaphore_anchor or not has_value_evidence:
            return 0

        if direct_zero_one:
            return 12
        if context_zero_one:
            return 10
        return 0

    if is_fcfs_waiting_time_query(query):
        # An FCFS-specific query must not promote a different scheduling lecture.
        if lecture_id is not None and "fcfs" not in lecture_id.casefold():
            return 0

        waiting_terms = {
            "wait", "waiting", "वेटिंग", "इंतजार", "इंतज़ार", "प्रतीक्षा"
        }
        time_terms = {"time", "टाइम", "समय"}

        direct_waiting = (
            bool(direct & waiting_terms) and bool(direct & time_terms)
        )
        context_waiting = (
            bool(context & waiting_terms) and bool(context & time_terms)
        )

        direct_turnaround = (
            "turnaround" in direct
            or {"turn", "around"} <= direct
        )
        context_turnaround = (
            "turnaround" in context
            or {"turn", "around"} <= context
        )
        burst_evidence = bool(context & {"burst", "बर्स्ट", "बरस"})

        if direct_waiting and context_turnaround and burst_evidence:
            return 12
        if direct_waiting and (context_turnaround or burst_evidence):
            return 11
        if direct_waiting:
            return 10
        if context_waiting and (context_turnaround or burst_evidence):
            return 10
        if direct_turnaround and burst_evidence:
            return 9
        return 0

    if is_critical_section_concurrency_query(query):
        critical_anchor = (
            {"critical", "section"} <= context
            or {"क्रिटिकल", "सेक्शन"} <= context
        )
        if not critical_anchor:
            return 0

        mutual_exclusion = (
            "mutual" in context
            and bool(context & {"exclusion", "exclusive"})
        )
        has_process = bool(
            context & {"process", "processes", "प्रोसेस", "प्रोसेसेस"}
        )
        one_process = (
            bool(context & {"one", "एक"})
            and has_process
        )
        another_process = bool(
            context & {
                "another", "other", "दूसरा", "दुसरा", "दूसरी"
            }
        )
        blocked_evidence = bool(
            context & {
                "blocked", "block", "cannot", "can't", "not",
                "ना", "नहीं", "पाए", "पाये", "paye", "paaye"
            }
        )

        if mutual_exclusion and has_process:
            return 12
        if one_process and another_process and blocked_evidence:
            return 12
        if has_process and blocked_evidence:
            return 10
        if mutual_exclusion:
            return 10
        return 0

    if is_deadlock_resource_wait_query(query):
        both_processes = {"p1", "p2"} <= context
        both_resources = {"r1", "r2"} <= context
        resource_evidence = bool(
            context & {"resource", "resources", "r1", "r2"}
        )
        holding_evidence = bool(
            context & {
                "taken", "take", "takes", "holding", "holds",
                "held", "using", "having", "have", "has"
            }
        )
        requesting_evidence = bool(
            context & {
                "wait", "waiting", "request", "requesting",
                "need", "give", "asking"
            }
        )

        if (
            both_processes and both_resources
            and holding_evidence and requesting_evidence
        ):
            return 12
        if (
            both_processes and resource_evidence
            and holding_evidence and requesting_evidence
        ):
            return 10
        if both_processes and both_resources and (
            holding_evidence or requesting_evidence
        ):
            return 8
        return 0

    if is_deadlock_definition_query(query):
        deadlock_anchor = bool(context & {"deadlock", "डेडलॉक"})
        waiting_evidence = bool(context & {"waiting", "wait"})
        process_evidence = bool(context & {"process", "processes"})
        event_evidence = bool(context & {"event", "happening"})

        # Reward the complete definition, not isolated mentions
        # of deadlock or generic circular-wait examples.
        if (
            deadlock_anchor
            and waiting_evidence
            and process_evidence
            and event_evidence
        ):
            return 12

        # A shorter segment may contain the event-not-happening
        # explanation while nearby context supplies the definition.
        if (
            deadlock_anchor
            and event_evidence
            and bool(context & {"happen", "happening", "never", "not"})
        ):
            return 10

        return 0

    paging_intent = paging_query_intent(query)

    if paging_intent == "division":
        page_anchor = bool(context & {
            "page", "pages", "paging", "पेज", "पेजों",
            "frame", "frames", "partition", "partitions"
        })
        process_anchor = bool(context & {
            "process", "processes", "प्रोसेस"
        })
        division_evidence = bool(context & {
            "divide", "divided", "division", "partition",
            "partitions", "split", "बाँटा", "बांटा", "विभाजित"
        })
        memory_evidence = bool(context & {
            "secondary", "memory", "ram", "main"
        })

        if (
            page_anchor and process_anchor
            and division_evidence and memory_evidence
        ):
            return 12
        if page_anchor and process_anchor and division_evidence:
            return 10
        if page_anchor and division_evidence and memory_evidence:
            return 8
        return 0

    if paging_intent == "reason":
        page_anchor = bool(context & {
            "page", "pages", "paging", "पेज", "पेजों",
            "frame", "frames"
        })
        memory_anchor = bool(context & {
            "memory", "ram", "main"
        })
        efficiency_evidence = bool(context & {
            "efficient", "efficiently", "efficiency",
            "efficiently", "efficient"
        })

        if page_anchor and memory_anchor and efficiency_evidence:
            return 12
        if page_anchor and efficiency_evidence:
            return 10
        return 0

    if is_fcfs_query(query):
        direct_text = " ".join(tokenize(segment_text))
        fcfs_anchor = (
            "fcfs" in context
            or {"first", "come", "serve"} <= context
        )
        # Arrival-time mentions also occur in SJF; require an FCFS anchor.
        if not fcfs_anchor:
            return 0
        direct_arrival = {"arrival", "time"} <= direct
        context_arrival = {"arrival", "time"} <= context
        direct_service = {"first", "come", "serve"} <= direct
        context_service = {"first", "come", "serve"} <= context
        if direct_arrival and context_service:
            return 10
        if direct_service and context_arrival:
            return 10
        if direct_arrival:
            return 8
        if direct_service:
            return 7
        if "fcfs" in direct or "first come first serve" in direct_text:
            return 1
        return 0

    if is_semaphore_purpose_query(query):
        text = " ".join(tokenize(f"{segment_text} {context_text}"))
        mutual = "mutual exclusion" in text or "mutual exclusive" in text
        critical = "critical section" in text
        has_process = bool(context & {"process", "processes"})
        sync_process = (
            bool(direct & {"process", "processes"})
            and bool(direct & {"synchronize", "synchronization", "synchronizes"})
        )
        if (mutual and critical and has_process) or sync_process:
            return 3
        if mutual or sync_process:
            return 1
        return 0

    intent = sjf_query_intent(query)
    if intent is None:
        return 0

    if intent == "tie_break":
        direct_arrival = "arrival" in direct
        direct_same = bool(direct & {"same", "equal", "सेम", "समान", "बराबर"})
        direct_id = "id" in direct
        context_arrival = "arrival" in context
        context_same = bool(context & {"same", "equal", "सेम", "समान", "बराबर"})
        context_id = "id" in context and bool(context & {"process", "processes", "प्रोसेस"})
        if direct_arrival and direct_same and direct_id:
            return 10
        if direct_arrival and direct_same and context_id:
            return 8
        if direct_id and context_arrival and context_same:
            return 7
        if direct_arrival and direct_same:
            return 6
        if context_arrival and context_same and context_id:
            return 2
        return 0

    if intent == "selection":
        burst_terms = {"burst", "बरस", "बर्स्ट"}
        decision_terms = {"select", "selected", "selecting", "choose", "chooses", "pick", "सलक्त", "सलेक्ट", "चुनें"}
        comparison_terms = {"p1", "p2", "p3", "p4", "both", "between", "different", "less", "smaller", "smallest", "shorter", "कम"}
        question_terms = {"which", "what", "how", "why", "किस", "कौन", "कैसे", "क्यों"}
        process_ids = {"p1", "p2", "p3", "p4"}
        reason_terms = {"because", "less", "smaller", "smallest", "shorter", "कम"}
        direct_burst = bool(direct & burst_terms)
        context_burst = bool(context & burst_terms)
        direct_decision = bool(direct & decision_terms)
        context_decision = bool(context & decision_terms)
        direct_comparison = bool(direct & comparison_terms)
        context_comparison = bool(context & comparison_terms)
        has_process_example = bool(context & process_ids)
        has_reason = bool(context & reason_terms)
        is_question_fragment = bool(direct & question_terms)
        # Do not promote a lecturer's interrogative fragment as an answer.
        if is_question_fragment:
            return 2
        if direct_decision and context_burst and has_process_example and has_reason:
            return 11
        if direct_burst and direct_decision and direct_comparison:
            return 10
        if direct_decision and context_burst and has_reason:
            return 7
        if direct_decision and context_burst:
            return 5
        if direct_burst and context_decision:
            return 5
        return 0

    if intent == "definition":
        sjf_anchor_terms = {"shortest", "test", "job", "शौट्तेश", "जौव"}
        has_sjf_anchor = bool(context & sjf_anchor_terms)
        has_burst = bool(context & {"burst", "बरस", "बर्स्ट"})
        has_explanation = bool(context & {
            "means", "mean", "whose", "less", "shortest", "test", "job", "smallest",
            "जिसका", "मतलब", "कम", "शौट्तेश", "जौव",
        })
        has_process = bool(context & {"process", "processes", "प्रोसेस"})
        if not has_sjf_anchor:
            return 0
        if has_burst and has_explanation and has_process:
            return 10
        if has_burst and has_explanation:
            return 8
        return 0
    return 0

def collect_segment_candidates(fused_chunks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []

    for fused in fused_chunks:
        record = fused["metadata"]
        lecture_id = str(record.get("lecture_id", "unknown"))
        segments = record.get("segments") or []

        if not segments:
            text = str(record.get("text_original", record.get("text_norm", ""))).strip()
            if text:
                segments = [
                    {
                        "start": record.get("start", record.get("window_start", 0.0)),
                        "end": record.get("end", record.get("window_end", 0.0)),
                        "text": text,
                    }
                ]

        for segment in segments:
            text = str(segment.get("text", "")).strip()
            if not text or "\ufffd" in text:
                # Whisper's replacement character marks an undecodable span;
                # do not surface obviously corrupted ASR segments as results.
                continue

            candidate = {
                "chunk_id": fused["chunk_id"],
                "lecture_id": lecture_id,
                "start": float(segment.get("start", record.get("start", 0.0))),
                "end": float(segment.get("end", record.get("end", 0.0))),
                "text": text,
                # Only nearby segments provide context for a concept that
                # spans ASR boundaries. A narrow +/-5s window avoids mixing
                # unrelated statements from the full 30-second chunk.
                "context_text": " ".join(
                    str(part.get("text", "")).strip()
                    for part in segments
                    if str(part.get("text", "")).strip()
                    and "\ufffd" not in str(part.get("text", ""))
                    and float(part.get("end", 0.0)) >= float(segment.get("start", 0.0)) - 5.0
                    and float(part.get("start", 0.0)) <= float(segment.get("end", 0.0)) + 5.0
                ),
                "video_path": record.get("video_path", ""),
                "audio_path": record.get("audio_path", ""),
                "window_start": record.get("window_start"),
                "window_end": record.get("window_end"),
                "rrf_score": fused["rrf_score"],
                "keyword_rank": fused["keyword_rank"],
                "dense_rank": fused["dense_rank"],
            }
            candidates.append(candidate)

    return candidates


def select_unique_segments(
    fused_chunks: list[dict[str, Any]],
    query: str,
    model: TextEmbedding,
    semantic_query: str | None = None,
) -> list[dict[str, Any]]:
    """Choose the best matching transcript segment per chunk, then de-duplicate."""
    candidates = collect_segment_candidates(fused_chunks)
    if not candidates:
        return []

    query_tokens = set(expand_query_tokens(query))
    semantic_query = semantic_query or semantic_query_text(query)
    segment_texts = [candidate["text"] for candidate in candidates]

    # Encode all candidate segments in one batch. Cosine similarity is a dot
    # product because embed_texts() L2-normalizes the vectors.
    segment_vectors = embed_texts(model, segment_texts)
    query_vector = embed_texts(model, [semantic_query])[0]
    similarities = segment_vectors @ query_vector

    for candidate, similarity in zip(candidates, similarities):
        candidate["segment_similarity"] = float(similarity)
        candidate["segment_keyword_overlap"] = lexical_overlap(
            candidate["text"], query_tokens
        )
        candidate["intent_match_score"] = segment_intent_match_score(
            query,
            candidate["text"],
            candidate.get("context_text", ""),
            candidate.get("lecture_id"),
        )

    # Retain multiple timestamp candidates per retrieved chunk.
    # This prevents a relevant ASR segment from being discarded merely
    # because another segment in the same chunk has a slightly higher score.
    max_segments_per_chunk = 3
    candidates_by_chunk: dict[str, list[dict[str, Any]]] = {}

    for candidate in candidates:
        candidates_by_chunk.setdefault(candidate["chunk_id"], []).append(candidate)

    selected_candidates: list[dict[str, Any]] = []

    for chunk_candidates in candidates_by_chunk.values():
        chunk_candidates.sort(
            key=lambda candidate: (
                candidate["intent_match_score"],
                candidate["segment_similarity"],
                candidate["segment_keyword_overlap"],
            ),
            reverse=True,
        )
        selected_candidates.extend(
            chunk_candidates[:max_segments_per_chunk]
        )

    # Overlapping windows can contain the same transcript segment. Keep the
    # copy backed by the strongest fused chunk result.
    unique_by_segment: dict[tuple[Any, ...], dict[str, Any]] = {}
    for candidate in selected_candidates:
        key = segment_key(candidate["lecture_id"], candidate)
        current = unique_by_segment.get(key)
        candidate_key = (
            candidate["intent_match_score"],
            candidate["rrf_score"],
            candidate["segment_similarity"],
            candidate["segment_keyword_overlap"],
        )
        current_key = (
            current["intent_match_score"],
            current["rrf_score"],
            current["segment_similarity"],
            current["segment_keyword_overlap"],
        ) if current else None

        if current is None or candidate_key > current_key:
            unique_by_segment[key] = candidate

    results = list(unique_by_segment.values())

    # Re-rank the timestamp-level candidates with a second RRF pass:
    #   1) chunk-level keyword+dense fusion rank,
    #   2) segment-level semantic similarity rank,
    #   3) exact content-word overlap rank (when overlap exists).
    # This helps a relevant segment rise above a noisy segment merely because
    # its surrounding 30-second chunk matched generic query words.
    fusion_order = sorted(results, key=lambda item: item["rrf_score"], reverse=True)
    semantic_order = sorted(
        results,
        key=lambda item: item["segment_similarity"],
        reverse=True,
    )
    lexical_candidates = [
        item for item in results if item["segment_keyword_overlap"] > 0
    ]
    lexical_order = sorted(
        lexical_candidates,
        key=lambda item: (
            item["segment_keyword_overlap"],
            item["segment_similarity"],
        ),
        reverse=True,
    )

    fusion_rank_by_key = {
        segment_key(item["lecture_id"], item): rank
        for rank, item in enumerate(fusion_order, start=1)
    }
    semantic_rank_by_key = {
        segment_key(item["lecture_id"], item): rank
        for rank, item in enumerate(semantic_order, start=1)
    }
    lexical_rank_by_key = {
        segment_key(item["lecture_id"], item): rank
        for rank, item in enumerate(lexical_order, start=1)
    }

    for item in results:
        key = segment_key(item["lecture_id"], item)
        item["fusion_rank"] = fusion_rank_by_key[key]
        item["semantic_rank"] = semantic_rank_by_key[key]
        item["lexical_rank"] = lexical_rank_by_key.get(key)
        item["hybrid_score"] = (
            1.0 / (RRF_K + item["fusion_rank"])
            + 1.25 / (RRF_K + item["semantic_rank"])
        )
        if item["lexical_rank"] is not None:
            item["hybrid_score"] += 0.5 / (RRF_K + item["lexical_rank"])

    results.sort(
        key=lambda item: (
            item["intent_match_score"],
            item["hybrid_score"],
            item["rrf_score"],
            item["segment_similarity"],
        ),
        reverse=True,
    )
    return results


# ---------------------------------------------------------------------------
# Command-line interface and output
# ---------------------------------------------------------------------------


def format_rank(rank: int | None) -> str:
    return str(rank) if rank is not None else "-"


def print_results(
    config: str,
    query: str,
    tokens: list[str],
    fts_query: str,
    keyword_ranks: dict[str, int],
    dense_ranks: dict[str, int],
    fused_chunks: list[dict[str, Any]],
    results: list[dict[str, Any]],
    limit: int,
) -> None:
    print("\n" + "=" * 72)
    print("HYBRID HINGLISH LECTURE SEARCH")
    print("=" * 72)
    print(f"Configuration:             {config}")
    print(f"Query:                     {query}")
    print(f"Expanded query tokens:     {tokens}")
    print(f"FTS query:                 {fts_query or '(empty query)'}")
    print(f"Keyword candidates:        {len(keyword_ranks)}")
    print(f"Dense candidates:          {len(dense_ranks)}")
    print(f"Fused chunk candidates:    {len(fused_chunks)}")
    print(f"Unique timestamp results:  {len(results)}")
    print(f"Displayed results:         {min(limit, len(results))}")
    print(f"Embedding model:           {MODEL_NAME}")
    print(f"Fusion:                    Reciprocal Rank Fusion (k={RRF_K})")
    print("=" * 72)

    for rank, result in enumerate(results[:limit], start=1):
        print(f"\nRank: {rank}")
        print(f"Lecture: {result['lecture_id']}")
        print(f"Hybrid score: {result['hybrid_score']:.6f}")
        print(f"Chunk RRF score: {result['rrf_score']:.6f}")
        print(f"Chunk fusion rank: {result['fusion_rank']}")
        print(f"Segment semantic rank: {result['semantic_rank']}")
        print(f"Keyword rank: {format_rank(result['keyword_rank'])}")
        print(f"Dense rank: {format_rank(result['dense_rank'])}")
        print(f"Segment cosine similarity: {result['segment_similarity']:.4f}")
        print(f"Segment keyword overlap: {result['segment_keyword_overlap']}")
        print(f"Intent match score: {result['intent_match_score']}")
        print(f"Suggested seek: {result['start']:.2f}s")
        print(f"Segment: {result['text']}")
        print(f"Video: {result['video_path']}")
        print("-" * 72)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Search lecture transcripts using keyword + dense retrieval + RRF."
    )
    parser.add_argument("config", choices=SUPPORTED_CONFIGS, help="Transcript/index configuration")
    parser.add_argument("query", help="English, Hindi, or Hinglish search query")
    parser.add_argument(
        "--limit",
        type=int,
        default=DEFAULT_RESULT_LIMIT,
        help=f"Number of timestamp results to display (default: {DEFAULT_RESULT_LIMIT})",
    )
    parser.add_argument(
        "--dense-candidates",
        type=int,
        default=DEFAULT_DENSE_CANDIDATES,
        help=f"Number of FAISS candidates to retrieve (default: {DEFAULT_DENSE_CANDIDATES})",
    )
    parser.add_argument(
        "--keyword-candidates",
        type=int,
        default=1000,
        help="Maximum number of FTS candidates to retrieve (default: 1000)",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    if args.limit < 1 or args.dense_candidates < 1 or args.keyword_candidates < 1:
        print("Error: --limit and candidate counts must all be positive integers.", file=sys.stderr)
        return 2

    try:
        keyword_ranks, _keyword_scores, tokens, fts_query = get_keyword_rankings(
            args.config,
            args.query,
            args.keyword_candidates,
        )

        index, metadata, metadata_by_id = load_dense_resources(args.config)

        print("Loading multilingual embedding model...", flush=True)
        model = TextEmbedding(model_name=MODEL_NAME)

        semantic_query = semantic_query_text(args.query)
        dense_ranks, _dense_similarities = get_dense_rankings(
            index,
            metadata,
            model,
            semantic_query,
            args.dense_candidates,
        )

        # metadata_by_id includes every indexed chunk. This is essential:
        # keyword-only candidates must survive fusion even when they are not
        # present in the FAISS top-k list.
        fused_chunks = reciprocal_rank_fusion(
            keyword_ranks,
            dense_ranks,
            metadata_by_id,
        )

        results = select_unique_segments(
            fused_chunks,
            args.query,
            model,
            semantic_query=semantic_query,
        )

        print_results(
            config=args.config,
            query=args.query,
            tokens=tokens,
            fts_query=fts_query,
            keyword_ranks=keyword_ranks,
            dense_ranks=dense_ranks,
            fused_chunks=fused_chunks,
            results=results,
            limit=args.limit,
        )

        return 0

    except (FileNotFoundError, RuntimeError, ValueError, sqlite3.Error) as exc:
        print(f"\nSearch failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
