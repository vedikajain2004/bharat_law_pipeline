"""
tests/test_chunker.py — Unit tests for the semantic chunker

Run with: pytest tests/test_chunker.py -v
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from chunker.chunker import chunk_document, TARGET_MIN_TOKENS, TARGET_MAX_TOKENS, HARD_MAX_TOKENS


# ── Fixture: synthetic legal markdown ─────────────────────────────────────────

SAMPLE_MD = """
<!-- page 1 -->

# Double Taxation Avoidance Agreements

## Introduction

India has entered into Double Taxation Avoidance Agreements (DTAAs) with over 90 countries.
These agreements help prevent the same income from being taxed in both countries.
The agreements are based on the OECD Model Convention and the UN Model Convention.
Under Section 90 of the Income-tax Act, 1961, the Central Government has the power to enter into such agreements.
A taxpayer can choose the more beneficial provisions between the DTAA and the Income Tax Act.

## Key Provisions

Article 7 of most DTAAs deals with business profits of a Permanent Establishment (PE).
A PE is defined as a fixed place of business through which the enterprise carries on its activities.
The definition of PE is crucial for determining the taxing rights of the source country.
Royalties and fees for technical services (FTS) are covered under Articles 12 and 13.
Dividends are typically taxed at reduced rates, often 5–15%, under the dividend article.

<!-- page 2 -->

## Treaty Benefits under DTAA

The taxpayer must be a tax resident of the contracting state to claim treaty benefits.
A Tax Residency Certificate (TRC) is mandatory under Section 90(4) of the Income-tax Act.
Form 10F must be filed along with the TRC for claiming treaty benefits.
The beneficial owner concept is applied to prevent treaty shopping.
The Principal Purpose Test (PPT) under the Multilateral Instrument limits abuse.

## Transfer Pricing

Transfer pricing provisions under Chapter X of the Income-tax Act apply to international transactions.
Arm's length price must be determined using prescribed methods under Rule 10B.
The Advance Pricing Agreement (APA) programme provides certainty on transfer pricing matters.
Mutual Agreement Procedure (MAP) under the DTAA resolves disputes between competent authorities.
Safe harbour rules under Rule 10TD provide certainty for routine transactions.

<!-- page 3 -->

## Country-Specific Notes

India–USA DTAA (1990) does not include a Limitation of Benefits (LOB) article.
India–Singapore DTAA was amended in 2016 to introduce source-based capital gains taxation.
India–Mauritius DTAA was amended in 2016 following concerns about treaty shopping.
India–Netherlands DTAA provides for arbitration as a dispute resolution mechanism.
India–UK DTAA has provisions for exchange of information between tax authorities.
""" * 3  # Repeat to ensure chunking happens across sections


def test_chunk_count_is_nonzero():
    chunks = chunk_document(SAMPLE_MD, "https://example.com", "abc123", "Test Doc")
    assert len(chunks) > 0, "Should produce at least one chunk"


def test_chunk_token_range():
    chunks = chunk_document(SAMPLE_MD, "https://example.com", "abc123", "Test Doc")
    non_tail = chunks[:-1]  # last chunk may be smaller
    for c in non_tail:
        assert c["token_estimate"] <= HARD_MAX_TOKENS, (
            f"Chunk {c['chunk_id']} exceeds hard max: {c['token_estimate']}"
        )


def test_chunk_required_fields():
    chunks = chunk_document(SAMPLE_MD, "https://example.com", "abc123", "Test Doc")
    required = {"chunk_id", "url", "title", "section_path", "page_no",
                "char_start", "char_end", "token_estimate", "text"}
    for c in chunks:
        missing = required - c.keys()
        assert not missing, f"Chunk {c['chunk_id']} missing fields: {missing}"


def test_chunk_ids_are_unique():
    chunks = chunk_document(SAMPLE_MD, "https://example.com", "abc123", "Test Doc")
    ids = [c["chunk_id"] for c in chunks]
    assert len(ids) == len(set(ids)), "Duplicate chunk IDs found"


def test_chunk_text_nonempty():
    chunks = chunk_document(SAMPLE_MD, "https://example.com", "abc123", "Test Doc")
    for c in chunks:
        assert c["text"].strip(), f"Empty text in chunk {c['chunk_id']}"


def test_page_numbers_tracked():
    chunks = chunk_document(SAMPLE_MD, "https://example.com", "abc123", "Test Doc")
    pages = {c["page_no"] for c in chunks}
    assert max(pages) >= 2, "Page numbers not tracked beyond page 1"


def test_section_path_populated():
    chunks = chunk_document(SAMPLE_MD, "https://example.com", "abc123", "Test Doc")
    with_path = [c for c in chunks if c["section_path"]]
    assert len(with_path) > 0, "No chunks have a section_path"


def test_char_offsets_ordered():
    chunks = chunk_document(SAMPLE_MD, "https://example.com", "abc123", "Test Doc")
    for c in chunks:
        assert c["char_start"] <= c["char_end"], (
            f"char_start > char_end in {c['chunk_id']}"
        )


def test_url_preserved():
    url = "https://example.com/test-page"
    chunks = chunk_document(SAMPLE_MD, url, "abc123", "Test Doc")
    for c in chunks:
        assert c["url"] == url
