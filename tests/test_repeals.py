from datetime import date

from taxlens.retrieval.repeals import (
    effective_date_in,
    ended_documents,
    explicit_targets,
    infer_repeals,
)


def test_list_of_ended_documents_takes_the_first_number_of_each_item():
    text = (
        "2. Nghị định này thay thế:\n"
        "a) Nghị định số 209/2013/NĐ-CP ngày 18 tháng 12 năm 2013 của Chính phủ.\n"
        "b) Nghị định số 49/2022/NĐ-CP sửa đổi Nghị định số 209/2013/NĐ-CP;\n"
        "c) Nghị định số 12/2015/NĐ-CP."
    )
    assert explicit_targets(text) == {"209/2013/nd-cp", "49/2022/nd-cp", "12/2015/nd-cp"}


def test_document_then_verb():
    text = "Luật Thuế giá trị gia tăng số 13/2008/QH12 hết hiệu lực kể từ ngày Luật này."
    assert explicit_targets(text) == {"13/2008/qh12"}


def test_verb_then_document():
    assert explicit_targets("Bãi bỏ Thông tư số 134/2014/TT-BTC của Bộ Tài chính.") == {
        "134/2014/tt-btc"
    }


def test_ending_part_of_a_document_is_ignored():
    assert not explicit_targets("Bãi bỏ khoản 7 Điều 11 Thông tư số 156/2013/TT-BTC.")
    assert not explicit_targets("Bãi bỏ nội dung ví dụ 37 tại Thông tư số 219/2013/TT-BTC.")


def test_document_that_continues_is_ignored():
    text = "Nghị định số 125/2020/NĐ-CP tiếp tục có hiệu lực cho đến khi có văn bản thay thế."
    assert not explicit_targets(text)


def test_effective_date():
    text = "Nghị định này có hiệu lực thi hành từ ngày 01 tháng 7 năm 2025."
    assert effective_date_in(text) == date(2025, 7, 1)


def test_guidance_and_amendment_follow_their_parent():
    titles = {
        "181/2025/NĐ-CP": "Quy định chi tiết Luật Thuế giá trị gia tăng",
        "209/2013/NĐ-CP": "Quy định chi tiết thi hành Luật Thuế giá trị gia tăng",
        "219/2013/TT-BTC": "Hướng dẫn thi hành Nghị định số 209/2013/NĐ-CP",
        "26/2015/TT-BTC": "Sửa đổi Thông tư số 219/2013/TT-BTC",
        "99/2020/TT-BTC": "Về một việc khác, có nhắc Nghị định số 209/2013/NĐ-CP",
    }
    ended = date(2025, 7, 1)
    repeals = infer_repeals([("209/2013/nd-cp", "181/2025/NĐ-CP", ended)], titles)
    assert {number: repeal.rule for number, repeal in repeals.items()} == {
        "209/2013/NĐ-CP": "explicit",
        "219/2013/TT-BTC": "guidance",
        "26/2015/TT-BTC": "amendment",
    }
    assert repeals["26/2015/TT-BTC"].ended_on == ended


def test_later_guidance_is_not_ended_by_an_earlier_repeal():
    titles = {
        "10/2024/NĐ-CP": "Nghị định cũ",
        "5/2026/TT-BTC": "Hướng dẫn Nghị định số 10/2024/NĐ-CP",
    }
    repeals = infer_repeals([("10/2024/nd-cp", "1/2025/NĐ-CP", date(2025, 1, 1))], titles)
    assert "5/2026/TT-BTC" not in repeals


def test_earliest_end_wins_and_a_document_cannot_end_itself():
    titles = {"1/2020/TT-BTC": "A", "2/2021/TT-BTC": "B"}
    repeals = infer_repeals(
        [
            ("1/2020/tt-btc", "9/2024/TT-BTC", date(2024, 1, 1)),
            ("1/2020/tt-btc", "8/2022/TT-BTC", date(2022, 1, 1)),
            ("2/2021/tt-btc", "2/2021/TT-BTC", date(2022, 1, 1)),
        ],
        titles,
    )
    assert repeals["1/2020/TT-BTC"].ended_on == date(2022, 1, 1)
    assert "2/2021/TT-BTC" not in repeals


def test_parent_outside_the_corpus_still_ends_its_guidance():
    titles = {"219/2013/TT-BTC": "Hướng dẫn thi hành Nghị định số 209/2013/NĐ-CP"}
    repeals = infer_repeals([("209/2013/nd-cp", "181/2025/NĐ-CP", date(2025, 7, 1))], titles)
    assert repeals["219/2013/TT-BTC"].rule == "guidance"


def test_guidance_of_a_named_law_follows_the_law_of_its_time():
    titles = {
        "13/2008/QH12": "Luật Thuế giá trị gia tăng",
        "48/2024/QH15": "Luật Thuế giá trị gia tăng",
        "1/2015/TT-BTC": "Hướng dẫn thi hành Luật Thuế giá trị gia tăng",
        "1/2025/TT-BTC": "Hướng dẫn thi hành Luật Thuế giá trị gia tăng",
    }
    repeals = infer_repeals([("13/2008/qh12", "48/2024/QH15", date(2025, 7, 1))], titles)
    assert repeals["1/2015/TT-BTC"].by == "13/2008/QH12"
    assert "1/2025/TT-BTC" not in repeals
    assert "48/2024/QH15" not in repeals


def test_document_does_not_end_with_the_one_it_replaces():
    titles = {
        "55/2010/TT-BTC": "A",
        "97/2026/TT-BTC": "Hướng dẫn, thay thế Thông tư số 55/2010/TT-BTC",
    }
    repeals = infer_repeals([("55/2010/tt-btc", "97/2026/TT-BTC", date(2026, 7, 6))], titles)
    assert "97/2026/TT-BTC" not in repeals


def test_ended_documents_by_date_and_rule():
    stored = {
        "A": {"ended_on": "2025-07-01", "rule": "explicit"},
        "B": {"ended_on": "2025-07-01", "rule": "guidance"},
        "C": {"ended_on": "2026-01-01", "rule": "explicit"},
    }
    assert ended_documents(stored, date(2025, 7, 1)) == ("A", "B")
    assert ended_documents(stored, date(2025, 6, 30)) == ()
    assert ended_documents(stored, date(2026, 1, 1), {"explicit"}) == ("A", "C")
