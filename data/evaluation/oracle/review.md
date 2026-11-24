# Oracle queries: first-pass review, for Le Hung to check

24/11/2026. Le Hung was to review the 30 draft queries ([plan](plan.md)). Short of time, he asked for a
first pass that he then checks. **This is that first pass, done by a Claude agent briefed as a Vietnamese
tax practitioner. It is not an expert's review, and the oracle result does not count until Le Hung has
checked it.**

How it was done: the agent saw the plan's four rules, each case's question, date, gold answer and gold
provisions, and the draft queries. It did not see how the drafts scored, so no rewrite is tuned to a
result. It read the provisions on public mirror sites (hethongphapluat.com, ketoanthienung.net,
luatvietnam.vn), not in the gazette and not in our corpus. Its full output is
[review-first-pass.json](review-first-pass.json); the proposed queries are in
[oracle-queries-reviewed.json](oracle-queries-reviewed.json). The drafts are unchanged.

## Outcome

- **14 kept, 16 rewritten, 1 added** (31 queries).
- 7 drafts were over 20 words (rule 1): A2.2, A5.1, A7.1, A7.2, A9.1, A22.1, L4.1. The drafting counted
  them wrongly.
- 9 rewrites correct the legal issue or its term: A2.3, A4.1, A6.2, A6.3, A9.2, A10.1, A15.1, A16.2,
  A20.1. Three of the over-long ones also named an issue their target does not hold (A2.2, A5.1, L4.1),
  and A7.2 named a second article.
- Added, A2.4: no draft aimed at the definition in Decree 181/2025 Art 4(1).
- The plan's "30 missed provisions" is 32 because R4 has one query for CIT Law Art 10(1), (2) and (3).
  The reviewer finds that one query enough.

## What Le Hung needs to decide

1. **The rewrites and the kept queries**, one by one, in the table below. The reviewer calls A4.1 and A20.1
   judgement calls (lay wording, not an error).
2. **Terms of art that rule 3 forbids.** "sơ chế thông thường", "hoạt động chăn nuôi" and "hoạt động
   trồng trọt" are four words each, so the natural queries for A2.1, A2.3, A6.2 and A6.3 cannot be written.
   Add them to the allowed names, or keep the paraphrases?
3. **"lãi chậm nộp"** stays in A4.3, A4.4 and A16.1. The statutory term is "tiền chậm nộp"; alternatives
   are in the table.
4. **"0%" in A20.1:** the name of the regime, or a rate that rule 4 forbids?
5. **"doanh nghiệp nhỏ", "doanh nghiệp vừa"** (A10.1, A11.1) are not CIT Law categories. Accept as
   shorthand?
6. **A7.1** fits Law 64/2025 Art 58(2) better than the missed clause 1 (see the gold-set doubts).

## Doubts about the gold set

Found in passing and not resolved. These matter beyond the oracle, since the same cases score retrieval.

1. **A7:** Decree 181/2025 Art 38(1) only gives the effective date, and Art 39 (transition) does not cover
   this refund. In Law 64/2025 Art 58 the rule for events that happened while a document was in force is
   clause 2, not the gold clause 1. The "may choose the policy" part of the answer needs a source.
2. **A14:** PIT Law 109/2025 takes general effect on 01/07/2026, after the case's 15/06/2026. Whether its
   business-income rules apply from the 2026 tax year was not verified, nor a reported 2026 amendment of
   Art 7(1).
3. **L4, A5:** the 5 million threshold is in the opening sentence of Decree 181/2025 Art 26, not in VAT
   Law Art 14(2).
4. **A2:** Decree 181/2025 Art 4 has clause 1b only through Decree 359/2025. Check that the corpus holds
   it and what the gold "Art 4(1)" should match. Circular 84/2025 Art 20(1)(c) is an amending clause that
   inserts the definition into Circular 26/2025.
5. **A10, A11, R4:** the revenue-basis sentence is an unnumbered paragraph after CIT Law Art 10(3). Check
   which clause the corpus files it under.
6. **A9:** Decree 125/2020 was reported amended from January 2026 (Decree 310/2025). Confirm the version
   that applies.

## Not verified

- Not read at all: Decree 125/2020 Art 9(2) (A9.2, from memory), Decree 181/2025 Art 4(1b) and Decree
  359/2025 Art 1(1) (A2.2), the end of Decree 181/2025 Art 4(1) and the instalment clause of Art 26, Law
  56/2024 Art 6(6), and the PIT Law's effective-date article.
- **Rule 3 on the 17 new wordings** was checked by eye only. `measure_oracle.py` must confirm it against
  the corpus; a wording that fails is rewritten again.
- Everything else was read on mirror sites, which can differ from the gazette.

## Next

1. Le Hung checks this page and edits `oracle-queries-reviewed.json` as he sees fit.
2. `python scripts/measure_oracle.py --queries data/evaluation/oracle/oracle-queries-reviewed.json
   --output data/evaluation/runs/oracle-reviewed.json` (minutes, no model calls, needs the database).
   Run it once, after his check, so the queries are not changed after a counted run (plan).

## Each query

| Query | Target | Verdict | Draft → proposed | Reviewer's reason | To check |
| --- | --- | --- | --- | --- | --- |
| A1.1 | 48/2024/QH15 9(3) | keep | mức thuế suất thuế giá trị gia tăng phổ thông cho các hàng hóa còn lại | VAT Law Art 9(3) is the residual standard-rate clause (goods and services not listed in clauses 1 and 2). The query names that issue without the rate; 'thuế suất phổ thông' is normal practitioner wording. |  |
| A1.2 | 174/2025/NĐ-CP 1(1) | keep | hàng hóa chịu thuế tiêu thụ đặc biệt có được giảm thuế giá trị gia tăng không | Decree 174/2025 Art 1(1)(b) excludes goods and services subject to special consumption tax (except petrol) from the VAT reduction. The query names exactly that issue. |  |
| A2.1 | 48/2024/QH15 5(1) | keep | sản phẩm rừng trồng chỉ bóc vỏ, phơi khô có phải chịu thuế giá trị gia tăng không | Art 5(1) (as replaced by Law 149/2025) governs non-taxable unprocessed or ordinarily processed crop, planted-forest, livestock and aquatic products. The query names it through two examples of ordinary processing. | The term of art 'sơ chế thông thường' is itself four words, so rule 3 forbids it; the draft uses the examples 'bóc vỏ, phơi khô' (which come from Decree 181 Art 4(1), not the Law). Decide whether the term should be added to the allowed names; if so, 'sản phẩm rừng trồng chỉ qua sơ chế thông thường có chịu thuế giá trị gia tăng không' would be the natural query. |
| A2.2 | 181/2025/NĐ-CP 4(1) | rewrite | doanh nghiệp mua nông sản, lâm sản chưa chế biến rồi bán lại cho công ty khác có phải kê khai thuế giá trị gia tăng → **mua nông sản, lâm sản bán lại cho doanh nghiệp khác có phải kê khai thuế giá trị gia tăng** | 26 words. Also mis-targeted: Decree 181 Art 4(1) (original text) only restates the exemption and defines ordinary processing; the trading-stage rule this query names sits in VAT Law Art 5(1) second paragraph (added by Law 149/2025) and in Decree 181 Art 4 clause 1b (added by Decree 359/2025). | Retarget this query to 48/2024 Art 5(1) (and 181 Art 4(1b) if it is in the corpus). A separate query for the Art 4(1) definition is proposed under coverage. I did not see the text of clause 1b (Decree 359), so the rewrite is not checked for 4-word runs against it. |
| A2.3 | 84/2025/TT-BNNMT 20(1) | rewrite | gỗ chỉ cưa xẻ, bóc vỏ có được coi là gỗ thô trong quy định về lâm sản → **gỗ chỉ cưa xẻ, bóc vỏ có được coi là gỗ sơ chế trong quy định về lâm sản** | Circular 84/2025 Art 20(1)(c) inserts the definition of 'gỗ sơ chế thông thường' into Circular 26/2025. The draft asks about 'gỗ thô', which is not the defined concept (the text only has 'gỗ xẻ thô' as one example); 'gỗ sơ chế' names the right concept without the 4-word term. | The full term 'gỗ sơ chế thông thường' is blocked by rule 3 (4 words). Confirm 'gỗ sơ chế' is acceptable shorthand. |
| A2.4 | 181/2025/NĐ-CP 4(1) | added | **những công đoạn nào được coi là sơ chế nông sản, lâm sản khi xét thuế giá trị gia tăng** | A2.2 was aimed at Art 4(1) but names the trading-stage rule, which Art 4(1) does not hold. Art 4(1) defines ordinary processing. | Checked for 4-word runs only against the first sentences of Art 4(1). |
| A3.1 | 38/2019/QH14 44(1) | keep | hạn chót nộp tờ khai thuế giá trị gia tăng hằng tháng là ngày nào | Tax Administration Law 38/2019 Art 44(1)(a) sets the deadline for monthly returns. The statutory term 'thời hạn nộp hồ sơ khai thuế' is the article title and cannot be used under rule 3; 'hạn chót nộp tờ khai' is a fair paraphrase. |  |
| A4.1 | 38/2019/QH14 47 | rewrite | sửa lại tờ khai đã gửi cơ quan thuế khi thấy có sai sót → **khai bổ sung tờ khai đã gửi cơ quan thuế khi thấy có sai sót** | Art 47 is 'khai bổ sung'; no practitioner searches 'sửa lại tờ khai'. The 3-word term of art can be used without breaking rule 3 (checked against Art 47(1): no 4-word run). | Judgement call: the draft is not legally wrong, only lay wording. Not checked against the text of Law 56/2024 Art 6(6). |
| A4.2 | 80/2021/TT-BTC 40(3) | keep | lô hàng xuất khẩu được hoàn thuế giá trị gia tăng rồi bị trả về thì xử lý ra sao | Circular 80/2021 Art 40(3) is specifically about VAT already refunded on exported goods that are then returned, so the scenario is the legal issue, not just the case's facts. | This query is close to a paraphrase of the user's question; that is unavoidable because the clause is that specific. It tests retrieval more than issue-naming. |
| A4.3 | 38/2019/QH14 59 | keep | khi nào người nộp thuế bị tính lãi chậm nộp | Art 59(1) lists the cases in which late-payment money is due; the query names that issue. | 'lãi chậm nộp' is colloquial; the statutory term is 'tiền chậm nộp'. A direct swap creates the statutory run 'tính tiền chậm nộp'. If you want the term of art: 'khi nào người nộp thuế phải chịu tiền chậm nộp' (10 words; Art 59 does not contain 'người nộp thuế phải chịu'). |
| A4.4 | 80/2021/TT-BTC 21 | keep | cách xác định số ngày và số tiền lãi chậm nộp thuế | Circular 80/2021 Art 21(1) governs how the late-payment amount is determined (amount, number of days, rate, period). The query names it. | Same 'lãi chậm nộp' vs 'tiền chậm nộp' point as A4.3. Note 'số ngày chậm nộp' and 'xác định số tiền chậm nộp' are statutory runs, so the term-of-art version must avoid them, e.g. 'cách xác định số ngày và khoản tiền chậm nộp thuế' (unverified by the script). |
| A5.1 | 48/2024/QH15 14(2) | rewrite | mua hàng trả dần chưa thanh toán qua ngân hàng có được khấu trừ thuế giá trị gia tăng đầu vào → **chưa thanh toán qua ngân hàng thì có được khấu trừ thuế giá trị gia tăng đầu vào không** | 21 words. VAT Law Art 14(2)(b) states only the general non-cash-payment condition for deduction; the instalment/deferred-payment rule is in Decree 181 Art 26, so 'mua hàng trả dần' is a case fact pointing at the decree, not at the target. | If you prefer to keep the instalment fact, the minimal trim is 'mua trả dần chưa thanh toán qua ngân hàng có được khấu trừ thuế giá trị gia tăng đầu vào' (20 words); note the term of art is 'trả chậm, trả góp', not 'trả dần'. |
| A6.1 | 48/2024/QH15 5(1) | keep | sản phẩm trồng trọt, chăn nuôi tự sản xuất bán ra có chịu thuế giá trị gia tăng không | Art 5(1) first paragraph covers products of growers and breeders who sell what they produce; the query names that issue correctly. |  |
| A6.2 | 32/2018/QH14 2(2) | rewrite | định nghĩa chăn nuôi theo luật chăn nuôi → **luật chăn nuôi coi những hoạt động nào là chăn nuôi** | The target is Art 2(2), the definition of 'hoạt động chăn nuôi'. 'Định nghĩa chăn nuôi' names Art 2(1) instead ('Chăn nuôi là ngành kinh tế - kỹ thuật...'). | The defined term 'hoạt động chăn nuôi' is itself four words, so rule 3 blocks the natural query 'hoạt động chăn nuôi là gì theo luật chăn nuôi'. Decide whether to exempt the defined term; otherwise use the rewrite. Low stakes: both clauses are in the same article. |
| A6.3 | 31/2018/QH14 2(2) | rewrite | định nghĩa trồng trọt theo luật trồng trọt → **luật trồng trọt coi những hoạt động nào là trồng trọt** | Same as A6.2: the target Art 2(2) lists what 'hoạt động trồng trọt' covers; 'định nghĩa trồng trọt' names Art 2(1). | Same question as A6.2 for the 4-word defined term 'hoạt động trồng trọt'. |
| A7.1 | 64/2025/QH15 58(1) | rewrite | khi quy định thay đổi giữa lúc phát sinh và lúc nộp hồ sơ thì dùng văn bản pháp luật nào → **quy định thay đổi giữa lúc phát sinh và lúc nộp hồ sơ thì dùng văn bản pháp luật nào** | 21 words; dropped the leading 'khi'. The issue (which legal document applies over time) is what Art 58 of the 2025 Law on Promulgation of Legal Documents governs. 'Áp dụng văn bản' is the article title (4 words), so 'dùng' stays. | Art 58(1) only says a document applies from when it takes effect; the rule for events that happened while a document was in force is Art 58(2). The query fits clause 2 better than the missed clause 1. |
| A7.2 | 181/2025/NĐ-CP 38(1) | rewrite | ngày có hiệu lực của nghị định hướng dẫn luật thuế giá trị gia tăng mới và chuyển tiếp hoàn thuế → **ngày có hiệu lực của nghị định hướng dẫn luật thuế giá trị gia tăng mới** | 21 words. Decree 181 Art 38(1) only states the effective date. Transitional rules are Art 39 (and concern investment projects and the 5% refund, not this case), so 'chuyển tiếp hoàn thuế' named a different article and is removed. | Confirm that Art 38(1) (effective date only) is the essential provision meant here; see gold-set doubts. |
| A9.1 | 38/2019/QH14 16(11) | rewrite | làm đúng công văn hướng dẫn của cục thuế nhưng sau đó bị xác định sai thì có bị phạt không → **làm đúng công văn hướng dẫn của cục thuế nhưng sau bị xác định sai thì có bị phạt không** | 21 words; dropped 'đó'. Art 16(11) (taxpayer's right not to be penalised or charged late-payment money when following written guidance) is the right provision. 'Cục thuế' is kept because 'của cơ quan thuế' is a statutory 4-word run. |  |
| A9.2 | 125/2020/NĐ-CP 9(2) | rewrite | những trường hợp được miễn xử phạt về thuế khi làm theo hướng dẫn của nhà nước → **trường hợp nào không bị phạt về thuế khi làm theo hướng dẫn của nhà nước** | Decree 125/2020 Art 9 is about 'không xử phạt' (no penalty at all). 'Miễn xử phạt' is a different institution (miễn tiền phạt, a later article of the same decree) and would pull the search there. | Art 9(2) content confirmed only from memory and a secondary summary, not the official text; the rewrite is therefore not checked for 4-word runs. 'Những trường hợp không' is the article title's opening and was avoided. |
| A10.1 | 67/2025/QH15 10(2) | rewrite | thuế suất thuế thu nhập doanh nghiệp ưu đãi cho doanh nghiệp nhỏ theo doanh thu năm → **thuế suất thuế thu nhập doanh nghiệp cho doanh nghiệp nhỏ theo doanh thu năm** | The rate in CIT Law Art 10(2) is not a 'thuế suất ưu đãi'; Art 10(1) itself separates it from incentive rates under Art 13. 'Ưu đãi' names the incentive regime, so it is removed. | 'Doanh nghiệp nhỏ' is not the Law's wording (it uses total annual revenue only); acceptable as practitioner shorthand? |
| A10.2 | 67/2025/QH15 10(3) | keep | doanh thu năm nào dùng làm căn cứ chọn thuế suất thuế thu nhập doanh nghiệp | The revenue-basis sentence (revenue of the immediately preceding tax period) follows clause 3 of Art 10; the query names that issue without the answer. | In the published text this sentence is an unnumbered paragraph after clause 3, before clause 4. Check how the corpus chunks it. |
| A11.1 | 67/2025/QH15 10(3) | keep | thuế suất thuế thu nhập doanh nghiệp cho doanh nghiệp vừa căn cứ doanh thu năm trước | Art 10(3) holds both the middle rate and the preceding-period revenue basis; the query names both without the rate or the thresholds. | 'Doanh nghiệp vừa' is not a statutory category in the CIT Law (and differs from the SME-support definition). 'Căn cứ doanh thu năm trước' hints at the revenue-basis rule but states no amount; I read it as issue, not answer. |
| A14.1 | 109/2025/QH15 7(4) | keep | cách tính thuế thu nhập cá nhân khi cho thuê nhà ở | PIT Law 109/2025 Art 7(4) sets how PIT is computed for individuals letting real estate. The query names it; 'nhà ở' is narrower than 'bất động sản' but natural. | See gold-set doubt on the PIT Law's effective date and a possible 2026 amendment of Art 7(1). |
| A15.1 | 108/2025/QH15 16(2) | rewrite | lãi phạt nộp thuế muộn được tính bao nhiêu phần trăm một ngày → **mức tiền chậm nộp thuế tính theo ngày là bao nhiêu phần trăm** | 'Lãi phạt nộp thuế muộn' is not a tax term and mixes two different things (a penalty and late-payment money). Law 108/2025 Art 16(2) is about 'tiền chậm nộp'. The rewrite avoids the statutory run 'mức tính tiền chậm nộp'. |  |
| A15.2 | 108/2025/QH15 16(1) | keep | những trường hợp phải trả tiền chậm nộp thuế | Law 108/2025 Art 16(1) opens with the list of cases in which late-payment money is due; the query names it with the correct term. | 'Phải trả' is slightly unnatural, but the natural 'phải nộp tiền chậm nộp' is a statutory run, so it cannot be improved without copying. |
| A16.1 | 108/2025/QH15 16(1) | keep | khai bổ sung làm tăng tiền thuế cần nộp có bị tính lãi chậm nộp không | Law 108/2025 Art 16(1)(b) is exactly the supplementary return that increases tax payable. This is the legal issue, not merely the case's facts; 'khai bổ sung' is used correctly. | 'Lãi chậm nộp' is colloquial for 'tiền chậm nộp'. Term-of-art alternative: 'khai bổ sung làm tăng tiền thuế cần nộp có phải chịu tiền chậm nộp không' (16 words). The query nearly restates the question, which is unavoidable here. |
| A16.2 | 108/2025/QH15 16(2) | rewrite | lãi phạt nộp thuế muộn tính theo tỷ lệ bao nhiêu mỗi ngày → **tiền chậm nộp thuế tính theo tỷ lệ bao nhiêu mỗi ngày** | Same defect as A15.1: 'lãi phạt nộp thuế muộn' is off-term; the provision is about 'tiền chậm nộp'. |  |
| A20.1 | 181/2025/NĐ-CP 18(1) | rewrite | hàng bán ra nước ngoài cần những chứng từ gì để được hưởng thuế suất 0% → **hàng xuất khẩu cần những chứng từ gì để được hưởng thuế suất 0%** | Decree 181 Art 18(1) is the conditions for the 0% rate for exported goods. 'Hàng bán ra nước ngoài' is not how anyone names exports; 'hàng xuất khẩu' is the term and does not copy four words. | Low stakes. The query contains '0%': I read it as the name of the regime (it is in the article title and in the user's question), not as the answer, so not a rule 4 breach. Confirm. |
| A22.1 | 181/2025/NĐ-CP 26(3) | rewrite | mua hàng nhiều lần trong ngày của cùng một người bán, trả tiền mặt, thuế đầu vào có được trừ không → **nhiều lần mua trong ngày từ một người bán bằng tiền mặt, thuế đầu vào có được khấu trừ không** | 21 words. Decree 181 Art 26(3) governs several same-day purchases from one taxpayer, so the issue is right. Reordered to avoid the statutory run 'mua nhiều lần trong cùng một ngày' and to use 'khấu trừ' rather than 'trừ'. |  |
| R4.1 | 67/2025/QH15 10(1)-(3) | keep | các mức thuế suất thuế thu nhập doanh nghiệp hiện hành theo quy mô doanh thu | CIT Law Art 10(1)-(3) sets the standard rate and the two revenue-based rates; the query names the set of rates by revenue size without stating any. | 'Hiện hành' is a time word but not a date; I read it as allowed under rule 2. |
| L4.1 | 48/2024/QH15 14(2) | rewrite | ngưỡng giá trị hàng mua phải trả qua ngân hàng mới được khấu trừ thuế giá trị gia tăng đầu vào → **điều kiện thanh toán qua ngân hàng để được khấu trừ thuế giá trị gia tăng đầu vào** | 21 words, and the issue is mis-stated for the target: VAT Law Art 14(2) contains no value threshold. The threshold is in the opening sentence of Decree 181 Art 26. Art 14(2)(b) governs the non-cash-payment condition itself, which the rewrite names. | A practitioner searching the threshold would expect the Decree, not the Law. If the threshold issue should stay as a query, aim it at Decree 181 Art 26, which is essential for L4 but not in its missed list. |
