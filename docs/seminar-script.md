# Seminar script, 11 Nov 2026

Draft script for two speakers in a 15-minute slot, in two parts: Tri presents Part 1, engineering
(slides 1-4, about 5:45 with a 4-minute live demo) and Hung presents Part 2, research (slides 5-13,
about 8:40). Khai does not speak, and joins for questions. That leaves about 0:35 of slack. Times
are targets. The deck keeps its current slides and all their content; the two glossary slides and the screenshot slide sit in backup. The speaker notes in Canva
also carry an "If asked" line with the finer research details. Figures come from
[evaluation-status.md](evaluation-status.md) and [retrieval-experiments.md](retrieval-experiments.md).

| # | Slide (current title) | Speaker | Time | Running |
| --- | --- | --- | --- | --- |
| 1 | Title | Tri | 0:20 | 0:20 |
| 2 | TaxLens Answers Tax Questions… + live demo | Tri | 4:00 | 4:20 |
| 3 | An Answer Is Only As Good As The Passages… | Tri | 0:50 | 5:10 |
| 4 | One API And One Database… (architecture, end of Part 1) | Tri | 0:35 | 5:45 |
| 5 | Problem: One Tax Question Can Need Several Laws (start of Part 2) | Hung | 1:00 | 6:45 |
| 6 | The Benchmark, Recall@10 and Coverage@10 | Hung | 1:15 | 8:00 |
| 7 | Coverage Failure vs Retrieval Failure | Hung | 0:40 | 8:40 |
| 8 | Even Our Best Search Finds Under Half… | Hung | 1:15 | 9:55 |
| 9 | Why Is So Much Missing? | Hung | 1:30 | 11:25 |
| 10 | Splitting The Question Into Legal Issues… | Hung | 1:00 | 12:25 |
| 11 | Next Test | Hung | 0:50 | 13:15 |
| 12 | We Can Now Measure Search… | Hung | 0:45 | 14:00 |
| 13 | Four Decisions Where Your View Would Help Most | Hung, then all | 0:25 | 14:25 |

## Before the talk

- Sign in and ask one question 5 minutes before the start. After idle, the first question waits a
  minute or more for the API to start; a warm site answers in 4 to 9 seconds.
- Keep the search term and the two demo questions in a text file, ready to paste.
- Take a screenshot of both answers during rehearsal, with date and time. If the site or the network
  fails, show them and say when they were taken.
- Rehearse the bottled-drink question. What the site returns for it is not recorded in the
  repository, so the script below does not assume a particular answer.
- If the demo passes 4:30, stop it and go to slide 3. Slide 4 can be cut to its first two sentences and slide 7 to one.

## 1. Title (Tri, 0:20)

Good morning. We are Tri, Hung and Khai. TaxLens answers Vietnamese tax questions from official law
texts. Today is about one question: does its search find every law an answer needs? The short answer
is no, and we think we know why. Let us start with the tool itself.

## 2. TaxLens and the live demo (Tri, 4:00)

*On the slide, 0:20.* TaxLens holds 2,991 official tax documents from the government portal and the
Ministry of Finance, split into about 145,000 passages, each one article or clause. It is a research
tool, not tax advice. Let me show it.

*Browser, Search tab, 0:50. Type a term without accents, such as "hoa don".*

First, search. I type without accents and it still finds "hóa đơn". Above are matching documents;
below are passages, ranked by keyword and by meaning together. Each passage shows its document,
article and clause.

*Ask tab, 1:10. Paste question 1, a short one-rule question chosen in rehearsal.*

Now a question. It searches the passages, sends the best ones to a language model, and the reply
comes back with numbered citations. Each citation names the document, article, clause and page, and
quotes the source text. If the passages do not answer the question, it says so instead of guessing.

*Ask tab, 1:30. Paste question 2: the bottled drink with 8 g of sugar per 100 ml, March 2026.*

Now a harder one. A company sells a bottled drink with 8 grams of sugar per 100 millilitres. What is
the VAT rate? The correct answer is 10%. But do not look at the number. Look at the Sources list.
A correct answer must rest on three provisions from three different laws. See which ones are here.
A right number does not show that search worked, and the rest of the talk is about the provisions
that are missing.

*Back to the slides.*

## 3. How an answer is made (Tri, 0:50)

Here is what just happened, and what we built. Official files are collected from the government
portal and the Ministry of Finance, read as text or by OCR, and split by article and clause into the
corpus. A question then goes to search: keyword matching finds the same words, vector search finds
similar meaning, and the two rankings are merged. The top passages go to the language model, which
writes the cited answer.

The part in blue is retrieval, and it is the only part we measure in the rest of the talk. The model
only sees what search hands it. If search misses a provision, the answer cannot be grounded in it.

## 4. What runs it (Tri, 0:35)

And this is what runs it. The browser talks to a Next.js web app, the only public service. It passes
each request to one FastAPI service, which does search, answers and the document library, and also
runs the long jobs: collecting, OCR and embedding. Airflow starts those jobs and polls them.
Everything is stored in one PostgreSQL database with full-text search and pgvector, plus Blob Storage
for the files. The answer model is hosted, reached through Hugging Face.

That was the engineering. Hung will take the research.

## 5. One question, three laws (Hung, 1:00)

Thank you, Tri. Now the research question: does search find every law an answer needs?
Back to the bottled drink. First, the special consumption tax law says a drink with more than
5 grams of sugar per 100 millilitres is a special-consumption good. Second, a decree excludes such
goods from the temporary 8% VAT rate. Third, the VAT law gives the normal rate, 10%.

Search finds the first step, around rank 5 to 10. It does not find the second or the third in the
top 200. The question says sugar and VAT rate; nothing in it mentions a temporary reduction. Miss
any one of the three and the answer is wrong or incomplete. So how do we measure this?

## 6. The benchmark and the two measures (Hung, 1:15)

We built an answer key from real tax-authority letters. For each case we list the
provisions a correct answer needs, mark each one essential or supporting, and fix an as-of date,
because the same facts can have a different answer in a different year. The table shows one case
with three dates and two answers.

We have 16 cases and 12 are scored. We run the question, take the top 10 passages, and count how
many essential provisions are there. For the bottled drink that is 1 of 3, so 0.33. That is recall
at 10, averaged over the cases.

Our second measure is stricter. Coverage at 10 asks: are all the essential provisions of a case in
the top 10? A case scores 1 only if every one is there, and Coverage at 10 is the share of cases
that do. The bottled drink scores 0. An answer needs every provision, so this is the measure that
matters most.

## 7. Coverage or retrieval? (Hung, 0:40)

A provision can be missed because the law is not in our collection, or because it is there and
search does not find it. We wrote rules for which documents enter the corpus before checking the
answer key, and the corpus grew to 2,991 documents. All 30 essential provisions are now in it. So
from here on, a miss is a search problem, not a data problem.

## 8. Results (Hung, 1:15)

Recall at 10, left to right. We started at 0.15, which turned out to be a bug: keyword search kept
only the first 12 words of a question. Fixing it gave 0.41. Adding documents dropped it to 0.30,
because old laws that have ended crowded the top 10. A filter that hides ended laws brought it to
0.45, our best result.

Three cautions. Twelve cases is small, so most differences are not significant. The filter is
partly inferred and not checked by an expert, so it is not on the live site. And results we reported
earlier were measured with a text-encoding bug, now repaired.

Now Coverage at 10. Even at our best it is 0.25: only 3 of 12 cases have every essential provision
in the top 10. The search on the live site covers 1 of 12. Why?

## 9. Why so much is missing (Hung, 1:30)

In the top 10 we miss 20 essential provisions. Five are found just below rank 10,
and one sits in no passage. The other 14 are not even in the top 200, so taking more results would
not help.

Of those 14, one uses different wording from the law. Six share words with the law, but the facts
of the case bury them. And seven, half of them, need a legal step the question never states. The
bottled drink has two of the seven.

This is the main finding. Better word matching cannot fix these seven, because the question does not
contain the words. Something has to work out which law the question depends on. One caution: the
grouping is our own reading, not a legal expert's.

## 10. What we tried, and why it lost (Hung, 1:00)

Our first attempt was issue-guided retrieval. A small language model splits the question into legal
issues; we search once per issue and merge the lists by taking turns.

It lost: 0.17 against 0.41, not significant, but clearly not a win. Taking turns pushed a good
result from rank 5 to rank 16. More important, the small model's issues were all about VAT. It never
asked whether the drink is a special-consumption good, so the hidden step stayed hidden. This
version lost; the idea was not really tested.

## 11. Next test (Hung, 0:50)

So the next experiment is an oracle test. We write the missing legal issues by hand for three cases,
before looking at any result and without naming any document. Do the hard provisions then reach the
top 10? If yes, the weak part is finding the issues. If no, the weak part is search itself. Either
answer tells us what to build. This is a plan: nothing has been run yet.

## 12. Summary (Hung, 0:45)

To sum up. We can now measure whether search finds the laws an answer needs. Our best setup fully
covers 3 of 12 cases, a Coverage at 10 of 0.25. Half of the provisions that cannot be found need a legal step the question
never states. Our first fix lost, and the oracle test will tell us why.

## 13. Four decisions (Hung, then all, 0:25)

We would like your view on four decisions: the ended-law filter, our essential labels, the number of
cases, and who should write the oracle issues. Thank you. We are happy to take questions.

## Backup slides

Shown only if asked: the screenshot slide ("A Correct Answer Can Hide Failed Retrieval"), the two
glossary slides, Appendix A (per-case results) and Appendix B (the 14 provisions).
