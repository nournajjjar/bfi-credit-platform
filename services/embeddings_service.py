"""
Cleaning → Semantic Chunking → Embedding → pgvector storage + semantic retrieval
(Uses sentence-transformers locally — no Azure embedding deployment required)
"""

import json
import re

import psycopg2
from psycopg2.extras import RealDictCursor
from sentence_transformers import SentenceTransformer

from core.config import DB_CONFIG
from core.logger import setup_logger


# ── Logger ────────────────────────────────────────────────────────────────────
logger = setup_logger(__name__)


# ── Local Embedding Model ─────────────────────────────────────────────────────
# Downloads ~80MB on first run, then cached locally forever.
# Dimension = 384  →  your pgvector column must be vector(384)
_embed_model = SentenceTransformer("paraphrase-multilingual-MiniLM-L12-v2")
EMBED_DIM     = 384
CHUNK_SIZE    = 400   # words per chunk (fallback splitter)
CHUNK_OVERLAP = 50


# ── Helper: local embed ───────────────────────────────────────────────────────
def _encode(texts: list[str]) -> list[list[float]]:
    """Encode a list of strings → list of 384-d float vectors."""
    vectors = _embed_model.encode(
        texts,
        normalize_embeddings=True,
        show_progress_bar=False,
        batch_size=32,
    )
    return [v.tolist() for v in vectors]


# ── 1. Cleaning ───────────────────────────────────────────────────────────────
def clean_json_data(data: dict, source: str) -> str:
    """
    Flatten structured JSON data into clean text
    for semantic chunking + embeddings.
    """

    lines = []

    try:

        # ──────────────────────────────────────────────────────────────────────
        # Deep Research Findings
        # ──────────────────────────────────────────────────────────────────────
        if source == "deep_research":

            findings = data.get("findings", {})

            for theme, items in findings.items():

                if not isinstance(items, list):
                    continue

                for item in items:

                    if not isinstance(item, dict):
                        continue

                    question = item.get("question", "")
                    answer   = item.get("answer", "")

                    if (
                        answer
                        and isinstance(answer, str)
                        and "non disponible" not in answer.lower()
                    ):
                        lines.append(
                            f"{theme.upper()} — {question}\n{answer}"
                        )

        # ──────────────────────────────────────────────────────────────────────
        # Financial PDF Extraction
        # ──────────────────────────────────────────────────────────────────────
        elif source == "pdf":

            for section, content in data.items():

                if section in ("raw_pages", "_meta"):
                    continue

                # Dict sections
                if isinstance(content, dict):
                    for key, value in content.items():
                        if value and value != "null":
                            lines.append(f"{section} / {key}: {value}")

                # List sections
                elif isinstance(content, list):
                    for page in content:
                        if not isinstance(page, dict):
                            continue
                        for table in page.get("tables", []):
                            for row in table.get("rows", []):
                                label  = row.get("label", "")
                                values = " | ".join(
                                    f"{k}: {v}"
                                    for k, v in row.get("values", {}).items()
                                    if v
                                )
                                if label and values:
                                    lines.append(f"{label}: {values}")

        # ──────────────────────────────────────────────────────────────────────
        # Final cleanup
        # ──────────────────────────────────────────────────────────────────────
        cleaned = "\n\n".join(lines)
        cleaned = re.sub(r"[^\w\s\.\,\:\-\(\)\/\%\+\n]", " ", cleaned)
        cleaned = re.sub(r"\s{3,}", "\n", cleaned)
        cleaned = cleaned.strip()

        logger.info(f"[Cleaning] Final cleaned length={len(cleaned)}")
        logger.info(f"[Cleaning] Preview={cleaned[:500]}")

        return cleaned

    except Exception as e:
        logger.error(f"[Cleaning] Failed: {str(e)}", exc_info=True)
        return ""


# ── 2. Semantic Chunking ──────────────────────────────────────────────────────
def chunk_text(text: str) -> list[str]:
    """
    Semantic chunking: split by paragraph boundaries first,
    then merge small paragraphs and split oversized ones.
    No external API needed.
    """

    try:
        logger.info("[Chunking] Starting semantic chunking")

        # Split on blank lines (natural paragraph boundaries)
        paragraphs = [p.strip() for p in re.split(r"\n{2,}", text) if p.strip()]

        chunks   = []
        buffer   = []
        buf_len  = 0

        for para in paragraphs:
            words = para.split()

            # If adding this paragraph keeps us under limit, buffer it
            if buf_len + len(words) <= CHUNK_SIZE:
                buffer.append(para)
                buf_len += len(words)

            else:
                # Flush current buffer
                if buffer:
                    chunks.append("\n\n".join(buffer))

                # If the paragraph itself is too big, hard-split it
                if len(words) > CHUNK_SIZE:
                    start = 0
                    while start < len(words):
                        end   = start + CHUNK_SIZE
                        chunk = " ".join(words[start:end])
                        if chunk.strip():
                            chunks.append(chunk.strip())
                        start += CHUNK_SIZE - CHUNK_OVERLAP
                    buffer  = []
                    buf_len = 0
                else:
                    buffer  = [para]
                    buf_len = len(words)

        # Flush remaining buffer
        if buffer:
            chunks.append("\n\n".join(buffer))

        logger.info(f"[Chunking] Created {len(chunks)} chunks")
        if chunks:
            logger.info(f"[Chunking] First chunk preview={chunks[0][:500]}")

        return chunks

    except Exception as e:
        logger.error(f"[Chunking] Failed: {str(e)}", exc_info=True)
        return []


# ── 3. Embedding Generation ───────────────────────────────────────────────────
def embed_chunks(chunks: list[str]) -> list[list[float]]:
    """
    Generate embeddings locally using sentence-transformers.
    No API key, no network call.
    """

    try:
        if not chunks:
            logger.warning("[Embedding] No chunks to embed")
            return []

        vectors = _encode(chunks)
        logger.info(f"[Embedding] Generated {len(vectors)} embeddings (dim={EMBED_DIM})")
        return vectors

    except Exception as e:
        logger.error(f"[Embedding] Failed: {str(e)}", exc_info=True)
        return []


# ── 4. Store Embeddings in pgvector ──────────────────────────────────────────
def store_embeddings(
    company:  str,
    source:   str,
    chunks:   list[str],
    vectors:  list[list[float]],
    metadata: dict = None,
):
    """
    Store semantic chunks + vectors in PostgreSQL pgvector.
    Make sure your table was created with vector(384).
    """

    conn = None

    try:
        conn = psycopg2.connect(**DB_CONFIG)

        with conn.cursor() as cur:

            # Delete previous embeddings for this company + source
            cur.execute(
                "DELETE FROM embeddings WHERE LOWER(company) = LOWER(%s) AND source = %s",
                (company, source),
            )

            for idx, (chunk, vector) in enumerate(zip(chunks, vectors)):
                cur.execute(
                    """
                    INSERT INTO embeddings
                        (company, source, chunk_index, chunk_text, metadata, embedding)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    """,
                    (company, source, idx, chunk, json.dumps(metadata or {}), vector),
                )

        conn.commit()
        logger.info(f"[Storage] Stored {len(chunks)} chunks for {company}")
        if chunks:
            logger.info(f"[Storage] Sample chunk={chunks[0][:500]}")

    except Exception as e:
        logger.error(f"[Storage] Failed: {str(e)}", exc_info=True)

    finally:
        if conn:
            conn.close()


# ── 5. Full Pipeline ──────────────────────────────────────────────────────────
def process_and_store(
    company:  str,
    source:   str,
    data:     dict,
    metadata: dict = None,
) -> int:
    """
    Full RAG pipeline:
    cleaning → semantic chunking → embeddings → pgvector storage
    """

    try:
        logger.info(f"[Pipeline] Processing {source} for {company}")

        cleaned_text = clean_json_data(data=data, source=source)
        if not cleaned_text:
            logger.warning(f"[Pipeline] No cleaned content for {company}")
            return 0

        chunks = chunk_text(cleaned_text)
        if not chunks:
            logger.warning(f"[Pipeline] No chunks created for {company}")
            return 0

        vectors = embed_chunks(chunks)
        if not vectors:
            logger.warning(f"[Pipeline] No vectors generated for {company}")
            return 0

        store_embeddings(
            company=company,
            source=source,
            chunks=chunks,
            vectors=vectors,
            metadata=metadata,
        )

        logger.info(f"[Pipeline] Successfully stored {len(chunks)} chunks")
        return len(chunks)

    except Exception as e:
        logger.error(f"[Pipeline] Failed: {str(e)}", exc_info=True)
        return 0


# ── 6. Semantic Retrieval ─────────────────────────────────────────────────────
def retrieve_relevant_chunks(
    company: str,
    query:   str,
    top_k:   int = 5,
) -> list[str]:
    """
    Semantic vector retrieval using pgvector cosine similarity.
    Query is embedded locally — no API call needed.
    """

    conn = None

    try:
        logger.info(f"[Retrieval] Company={company}")
        logger.info(f"[Retrieval] Query={query}")

        # Embed the query locally
        query_vector = _encode([query])[0]

        logger.info("[Retrieval] Query embedding generated")

        conn = psycopg2.connect(**DB_CONFIG)

        with conn.cursor(cursor_factory=RealDictCursor) as cur:

            cur.execute(
                """
                SELECT
                    chunk_text,
                    source,
                    1 - (embedding <=> %s::vector) AS similarity
                FROM embeddings
                WHERE LOWER(company) = LOWER(%s)
                ORDER BY embedding <=> %s::vector
                LIMIT %s
                """,
                (query_vector, company, query_vector, top_k),
            )

            rows = cur.fetchall()

        logger.info(f"[Retrieval] Retrieved {len(rows)} chunks")
        for idx, row in enumerate(rows):
            logger.info(f"[Retrieval] Chunk {idx} similarity={row['similarity']:.4f}")

        chunks = [row["chunk_text"] for row in rows if row.get("chunk_text")]

        if chunks:
            logger.info(f"[Retrieval] First chunk preview={chunks[0][:500]}")

        return chunks

    except Exception as e:
        logger.error(f"[Retrieval] Failed: {str(e)}", exc_info=True)
        return []

    finally:
        if conn:
            conn.close()