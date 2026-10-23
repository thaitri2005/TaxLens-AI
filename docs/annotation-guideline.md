# TaxLens – Annotation Guideline v1 (21/10/2026)

The gold set lives in `data/evaluation/gold_set_v1.csv`; how it is scored is in [retrieval.md](retrieval.md#gold-set).

**Summary (5 lines)**
1. Each case = one taxpayer situation + one date + the full list of laws needed to answer it.
2. Gold laws come only from the original letter (công văn) or the law text, never from news or summaries.
3. Every gold law is labelled **E (essential)** or **S (supporting)**; main scores use E only.
4. Gold laws must be the version in force on the case's `as_of_date`.
5. When unsure: mark `uncertain = Y`, write why, and discuss in the pair. Never guess.

---

## Step 1 – Case record fields

| Field | Rule |
|---|---|
| `case_id` | Unique code (A1…, R1…, L1…) |
| `source` | Letter number, issuer, issue date; `source_verified = Y` only if the full original text was read |
| `as_of_date` | One exact date taken from the situation the question describes. If the question gives a period, choose a day well inside it, never on its edge |
| `filing_date` | Optional; only when a procedure date matters (e.g. refund filed after a law change) |
| `question` | Your own plain wording, not copied from the letter; must state the date or period |
| `gold_answer` | Short correct answer (key points only) |
| `gold_provisions` | One item per law, separated by ` \| `: label E/S + document + article/clause/point, e.g. `E: Decree 181/2025 Art 16(2)(a)`. Always write the document's number and year the first time it appears in a case; later items may shorten it (`Decree 181 Art 19(3)`, `VAT Law Art 9(3)`). Notes go after `, ` or in ` (...)`. Write `(none)` for no provisions. |
| `case_type` | answerable / conditional / false premise / leakage-free |
| `derived_from` | For a leakage-free case, the `case_id` it was rewritten from |
| `annotator`, `minutes_spent`, `uncertain`, `notes` | Who, how long, doubts |

## Step 2 – Essential (E) vs supporting (S)

**Test for E:** *"If this law were missing, could a careful reader give a wrong or incomplete answer?"* Yes → E. No → S.

Typical S: general articles the letter cites as background, procedure or invoice rules the question does not ask about, rules for other buyers or other periods.

**Expansion rules (check that nothing is missing):**
- **T1 Main rule** – the article that directly answers.
- **T2 Definition elsewhere** – if the answer depends on a category defined in another law or circular, add it.
- **T3 Exception / temporary rule** – if an exception or time-limited rule could change the answer, add it.
- **T4 Guidance** – if the law says "Chính phủ / Bộ … quy định chi tiết", add the decree or circular clause that details it.
- **T5 Time** – keep only versions valid on `as_of_date` (Step 3).

An amended provision and its amending provision count as **one** gold item, written as: *"Law 48/2024 Art 5(1), as amended by Law 149/2025 Art 1(1)(a)"*.

## Step 3 – Dates and versions

- A gold law counts only if it is the version in force on `as_of_date`.
- Choose `as_of_date` inside the period the **letter** dealt with, so the letter's citations stay valid. Key change dates to avoid crossing by accident: **1/7/2025** (VAT Law 48/2024), **1/1/2026** (Law 149/2025, Decree 359/2025), **20/6/2026** (Decree 144/2026), **1/7/2026** (Tax Administration Law 108/2025 and its guidance).
- If a law changed after the letter, either keep `as_of_date` before the change, or re-annotate with the new law and note it.

## Step 4 – Level of detail

- Record to **clause (khoản)**, and to **point (điểm)** when the letter gives it.
- Scoring: *exact* = same document + article + clause; *partial* = same document + article; anything else = missed.
- Retrieval unit in the corpus = one clause.

## Step 5 – When unsure

- Mark `uncertain = Y` and write the doubt in `notes`.
- Original text not available → `source_verified = N`; the case cannot enter the final benchmark until verified.
- Disagreements in the pair → discuss; still unresolved → list for the tax experts.

## Process

- Two people annotate at least 50 cases independently → report Cohen's kappa on E labels.
- Log `minutes_spent`; if the average exceeds 30 minutes per case, simplify before scaling up.
