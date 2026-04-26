"""
tests/test_ner.py — NER breadth tests for Indian legal text

Tests are organised by real Indian law citation conventions, NOT derived
from gold_ner.jsonl. Each parametrize set covers a distinct citation grammar
actually used in Indian statutes, tribunal orders, and CBDT circulars.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from ner.ner_engine import (
    extract_entities,
    _regex_entities,
    _PATTERNS,
)


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION_REF — full citation grammar
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("text,contains", [
    # Plain section
    ("under Section 10 of the Act",               "Section 10"),
    # Section with capital-letter suffix
    ("Section 9A inserted by Finance Act",         "Section 9A"),
    # Section with parenthesised sub-sections
    ("Section 2(1)(a) defines assessee",           "Section 2(1)(a)"),
    ("as per Section 1(2) of the Rules",           "Section 1(2)"),
    # Sub-section reference
    ("Sub-section (3) of Section 40A applies",     "Sub-section (3) of Section 40A"),
    # Clause-level reference
    ("Clause (b) of Section 10(23C) exempts",      "Clause (b) of Section 10(23C)"),
    # Clause of Sub-section of Section
    ("Clause (a) of Sub-section (1) of Section 80C", "Clause (a) of Sub-section (1) of Section 80C"),
    # Proviso
    ("first proviso to Section 44AD applies",      "first proviso to Section 44AD"),
    ("proviso to Sub-section (2) of Section 139", "proviso to Sub-section (2) of Section 139"),
    # Explanation
    ("Explanation 2 to Section 9(1)(vi)",          "Explanation 2 to Section 9(1)(vi)"),
    ("Explanation to Section 43B",                 "Explanation to Section 43B"),
    # Schedule
    ("Fourth Schedule to the Act",                 "Fourth Schedule"),
    ("as per the Seventh Schedule",                "Seventh Schedule"),
    # Order-Rule (CPC style)
    ("Order I Rule 8 of the Code",                 "Order I Rule 8"),
    ("Order XXXIX Rule 1",                         "Order XXXIX Rule 1"),
    # Rule (Income Tax Rules)
    ("Rule 10B prescribes methods",                "Rule 10B"),
    ("under Rule 114 of the Rules",               "Rule 114"),
    # Chapter
    ("Chapter VI-A deductions",                    "Chapter VI-A"),
    ("under Chapter X of the Act",                 "Chapter X"),
    # Constitutional Article
    ("Article 265 of the Constitution",            "Article 265"),
    ("Article 14 guarantees equality",             "Article 14"),
    # Paragraph
    ("para 4 of the Circular applies",             "para 4"),
])
def test_section_ref(text, contains):
    ents = [e for e in extract_entities(text) if e.label == "SECTION_REF"]
    found = [e.text for e in ents]
    assert any(contains in t for t in found), (
        f"Expected SECTION_REF containing {contains!r}\n  text: {text!r}\n  found: {found}"
    )


# ═══════════════════════════════════════════════════════════════════════════════
# NOTIFICATION — all Indian gazette / circular families
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("text,contains", [
    # Gazette notifications
    ("vide S.O. 3696(E) dated",                   "S.O. 3696(E)"),
    ("notification G.S.R. 237(E) issued",         "G.S.R. 237(E)"),
    ("S.O. 999 published in gazette",             "S.O. 999"),
    # CBDT Circulars
    ("CBDT Circular No. 3/2024 clarifies",        "CBDT Circular No. 3/2024"),
    ("as per Circular No. 13/2023",               "Circular No. 13/2023"),
    ("Circular No. 7 of 2019 applies",            "Circular No. 7 of 2019"),
    # Instructions
    ("Instruction No. 2/2022 issued by CBDT",     "Instruction No. 2/2022"),
    # File numbers
    ("F.No. 225/12/2024-ITA-II refers",           "F.No. 225/12/2024-ITA-II"),
    # Notification number
    ("Notification No. 56/2023 dated",            "Notification No. 56/2023"),
    # Press Release
    ("Press Release No. 402/92/2006-MC",          "Press Release No. 402/92/2006"),
])
def test_notification(text, contains):
    ents = [e for e in extract_entities(text) if e.label == "NOTIFICATION"]
    found = [e.text for e in ents]
    assert any(contains in t for t in found), (
        f"Expected NOTIFICATION containing {contains!r}\n  text: {text!r}\n  found: {found}"
    )


# ═══════════════════════════════════════════════════════════════════════════════
# DATE — all Indian legal date formats
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("text,contains", [
    # ISO
    ("effective from 2023-04-01",                 "2023-04-01"),
    # DD-MM-YYYY
    ("dated 31-03-2024",                          "31-03-2024"),
    # DD/MM/YYYY
    ("filed on 30/10/2022",                       "30/10/2022"),
    # DD.MM.YYYY
    ("on 01.04.2023 the rate",                    "01.04.2023"),
    # DD Month YYYY
    ("the order of 31 August 2020",               "31 August 2020"),
    ("on 12th March, 2024",                       "12th March, 2024"),
    # Month DD, YYYY
    ("as of March 31, 2024",                      "March 31, 2024"),
    # Month YYYY only
    ("in April 2019 the CBDT",                    "April 2019"),
    # Fiscal / Assessment year
    ("for FY 2023-24 the limit",                  "FY 2023-24"),
    ("for A.Y. 2024-25 applies",                  "A.Y. 2024-25"),
    # w.e.f.
    ("w.e.f. 01-04-2023 new rates",               "w.e.f. 01-04-2023"),
])
def test_date(text, contains):
    ents = [e for e in extract_entities(text) if e.label == "DATE"]
    found = [e.text for e in ents]
    assert any(contains in t for t in found), (
        f"Expected DATE containing {contains!r}\n  text: {text!r}\n  found: {found}"
    )


# ═══════════════════════════════════════════════════════════════════════════════
# MONEY — Indian number system + foreign currencies
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("text,contains", [
    # Indian number system with symbol
    ("penalty of ₹95,79,089 imposed",             "₹95,79,089"),
    ("₹50 lakh threshold",                        "₹50"),
    # Rs. forms
    ("Rs. 1,00,000 deductible",                   "Rs. 1,00,000"),
    ("Rs.500 registration fee",                   "Rs.500"),
    # INR
    ("INR 12,07,935 recovered",                   "INR 12,07,935"),
    # Words — crore/lakh
    ("2.5 crore rupees penalty",                  "2.5 crore rupees"),
    ("50 lakh rupees deposited",                  "50 lakh rupees"),
    # Foreign
    ("USD 35,152 remitted",                       "USD 35,152"),
    ("EUR 10,000 transferred",                    "EUR 10,000"),
])
def test_money(text, contains):
    ents = [e for e in extract_entities(text) if e.label == "MONEY"]
    found = [e.text for e in ents]
    assert any(contains in t for t in found), (
        f"Expected MONEY containing {contains!r}\n  text: {text!r}\n  found: {found}"
    )


# ═══════════════════════════════════════════════════════════════════════════════
# ACT_NAME — gazetteer + heuristic
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("text,contains", [
    # Core gazetteer entries
    ("under the Income-tax Act, 1961 the assessee", "Income-tax Act, 1961"),
    ("the Foreign Exchange Management Act, 1999",   "Foreign Exchange Management Act, 1999"),
    ("the Companies Act, 2013 mandates",            "Companies Act, 2013"),
    ("Insolvency and Bankruptcy Code, 2016",        "Insolvency and Bankruptcy Code, 2016"),
    ("Code of Civil Procedure, 1908",               "Code of Civil Procedure, 1908"),
    ("Prevention of Money Laundering Act, 2002",    "Prevention of Money Laundering Act, 2002"),
    # New Indian codes (post-2023)
    ("Bharatiya Nyaya Sanhita, 2023 replaces",      "Bharatiya Nyaya Sanhita, 2023"),
    ("Bharatiya Sakshya Adhiniyam, 2023",           "Bharatiya Sakshya Adhiniyam, 2023"),
    # Heuristic — NOT in gazetteer
    ("the Cryptocurrency Regulation Act, 2025",     "Cryptocurrency Regulation Act, 2025"),
    ("under the Digital Personal Data Protection Act, 2023", "Digital Personal Data Protection Act, 2023"),
])
def test_act_name(text, contains):
    ents = [e for e in extract_entities(text) if e.label == "ACT_NAME"]
    found = [e.text for e in ents]
    assert any(contains in t for t in found), (
        f"Expected ACT_NAME containing {contains!r}\n  text: {text!r}\n  found: {found}"
    )


# ═══════════════════════════════════════════════════════════════════════════════
# ORG — Indian courts, tribunals, regulators
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("text,contains", [
    ("the Supreme Court of India held",             "Supreme Court of India"),
    ("the Delhi High Court dismissed",              "Delhi High Court"),
    ("Income Tax Appellate Tribunal upheld",        "Income Tax Appellate Tribunal"),
    ("Central Board of Direct Taxes issued",        "Central Board of Direct Taxes"),
    ("the Reserve Bank of India directed",          "Reserve Bank of India"),
    ("Securities and Exchange Board of India",      "Securities and Exchange Board of India"),
    ("National Company Law Tribunal order",         "National Company Law Tribunal"),
    ("the Enforcement Directorate attached",        "Enforcement Directorate"),
    ("Ministry of Finance notification",            "Ministry of Finance"),
    ("Comptroller and Auditor General of India",    "Comptroller and Auditor General of India"),
])
def test_org(text, contains):
    ents = [e for e in extract_entities(text) if e.label == "ORG"]
    found = [e.text for e in ents]
    assert any(contains in t for t in found), (
        f"Expected ORG containing {contains!r}\n  text: {text!r}\n  found: {found}"
    )


# ═══════════════════════════════════════════════════════════════════════════════
# Integration — realistic Indian legal sentences
# ═══════════════════════════════════════════════════════════════════════════════

REALISTIC_SENTENCES = [
    {
        "text": (
            "The Supreme Court of India, in its order dated 31 August 2020, "
            "upheld the validity of Section 9(1)(i) of the Income-tax Act, 1961, "
            "observing that the Central Board of Direct Taxes had correctly issued "
            "Circular No. 7 of 2019 to clarify the scope of royalty income."
        ),
        "expected": {"ORG", "DATE", "SECTION_REF", "ACT_NAME", "NOTIFICATION"},
    },
    {
        "text": (
            "The Income Tax Appellate Tribunal, Mumbai bench, held that the "
            "Explanation 2 to Section 9(1)(vi) does not apply to software payments "
            "made under the DTAA with the USA. The AO had demanded ₹2,45,67,890 "
            "as withholding tax for FY 2021-22."
        ),
        "expected": {"ORG", "SECTION_REF", "MONEY", "DATE"},
    },
    {
        "text": (
            "Vide Notification No. 56/2023 dated 01-06-2023, the Ministry of Finance "
            "amended Rule 10TD of the Income-tax Rules, 1962 to revise the safe harbour "
            "margins w.e.f. 01-04-2023. The changes apply from A.Y. 2024-25 onwards."
        ),
        "expected": {"NOTIFICATION", "DATE", "ORG", "SECTION_REF", "ACT_NAME"},
    },
    {
        "text": (
            "The Enforcement Directorate attached assets worth Rs. 45,32,000 under "
            "Section 5 of the Prevention of Money Laundering Act, 2002, pursuant to "
            "F.No. 05/07/2023-ED and G.S.R. 441(E) issued on 12th March, 2024."
        ),
        "expected": {"ORG", "MONEY", "SECTION_REF", "ACT_NAME", "NOTIFICATION", "DATE"},
    },
]

@pytest.mark.parametrize("case", REALISTIC_SENTENCES)
def test_realistic_sentence(case):
    ents = extract_entities(case["text"])
    found_labels = {e.label for e in ents}
    missing = case["expected"] - found_labels
    assert not missing, (
        f"Missing labels: {missing}\n"
        f"  text: {case['text'][:80]}...\n"
        f"  found: {[(e.label, e.text) for e in ents]}"
    )


# ═══════════════════════════════════════════════════════════════════════════════
# Structural invariants
# ═══════════════════════════════════════════════════════════════════════════════

def test_no_overlapping_spans():
    """No two returned entities may share a character position."""
    text = (
        "G.S.R. 45(E) dated 19 December 2017, penalty ₹4,51,664, "
        "proviso to Section 2(1)(a) of Code of Civil Procedure, 1908, "
        "upheld by Supreme Court of India on 31-03-2024."
    )
    ents = extract_entities(text)
    for i, a in enumerate(ents):
        for b in ents[i+1:]:
            overlap = max(0, min(a.end, b.end) - max(a.start, b.start))
            assert overlap == 0, f"Overlapping: {a!r} vs {b!r}"


def test_entities_within_text_bounds():
    text = "Section 80C of the Income-tax Act, 1961 allows deduction of Rs. 1,50,000."
    for e in extract_entities(text):
        assert 0 <= e.start < e.end <= len(text), f"Out-of-bounds entity: {e}"
        assert text[e.start:e.end].strip() != "", f"Empty span: {e}"


def test_empty_text():
    assert extract_entities("") == []


def test_plain_english_no_false_positives():
    """Generic English prose should not trigger Indian legal labels."""
    text = "The company released its annual report today showing strong growth."
    ents = extract_entities(text)
    legal_labels = {"SECTION_REF", "NOTIFICATION", "ACT_NAME"}
    false_positives = [e for e in ents if e.label in legal_labels]
    assert not false_positives, f"False positives on plain text: {false_positives}"
