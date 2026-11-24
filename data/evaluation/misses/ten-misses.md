# The 10 provisions missed even when their issue is named

24/11/2026. The counted oracle run left 10 of the 32 missed provisions outside the top 20 of every
search, the question's and the reviewed issue queries'. `ten_misses.py` ranked each in the keyword and
vector lists separately, 500 deep, with the case's filters, read its passage, and listed what outranks
it. All pass the filters (in force on the case's date, not ended).

| Provision | Best keyword / vector rank (any query) | Cause |
| --- | --- | --- |
| A1: VAT Law 48/2024 9(3) | none / none | **Content-free clause**: "10% applies to goods not in clauses 1 and 2". Nothing in it names a subject |
| A7: Decree 181/2025 38(1) | none / none | **Content-free clause**: one line, the effective date (and a gold doubt in the review) |
| A15, A16: Law 108/2025 16(1) | 15 (A16 issue) / 182 | **Sibling found, not this clause**: 16(2) (the rate) is in the issue's top 5-15; 16(1) (the cases) is split across two passages, one starting mid-sentence |
| A3: Tax Admin. Law 38/2019 44(1) | none / 77 | **Words differ**: the law says "thời hạn nộp hồ sơ khai thuế", people say "hạn chót nộp tờ khai"; 2021-2025 deadline-extension decrees fill the top |
| A14: PIT Law 109/2025 7(4) | none / 20 | **Words differ**: "cho thuê bất động sản" against "cho thuê nhà"; the 2013 PIT circular 111/2013 (no ending stated) is first |
| A7: Law 64/2025 58(1) | none / 23 | **Words differ**, vector only; fusion drops a passage that only one list finds |
| A4: Tax Admin. Law 38/2019 59 | 32 / 49 | **Old law crowds it**: 83/2013, 28/2011 (endings only inferred), 176/2010, 39/1997 |
| A2: VAT Law 48/2024 5(1) | none / 52 | **Old law crowds it**: 1990s and 2012-2013 texts on VAT deferral and exemptions |
| A2: Decree 181/2025 4(1) | none / none | **Long OCR'd part**: article 4 is 10 parts with no clause numbers; the target is a 1,435-character part with OCR noise covering several items |

The inferred ending rules would not rescue them: with all rules, the best ranks move only for A4 (29 →
20), A14 (35 → 31), and A16 (29 → 22).

## Article expansion: ceiling

Four of the ten sit in an article that search does reach (a sibling clause), or are clauses that only
make sense with their article. `article_ceiling.py` scored the 30 questions' hybrid top 20 counting a
provision as found when any passage of its article is in the top K (report
`article-ceiling-gold34-item19.json`):

| | K = 5 | K = 10 | K = 20 |
| --- | --- | --- | --- |
| Clause, as scored today | 0.31 | 0.47 | 0.53 |
| Article: answers would get the whole article of each passage | **0.43** | 0.55 | 0.58 |

Gains at K = 5 in A17, A18, A19, L4 (and A1, A14, A21 at K = 10-20). This is a ceiling: it assumes the
answer reads each top passage's whole article, and the top 5 hold a median of 4 articles, some long (VAT
Law Art 5 has 29 passages). A design must cap the added text and be measured on answers.
