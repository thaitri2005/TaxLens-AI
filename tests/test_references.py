from taxlens.retrieval.references import LegalReference, find_references


def test_point_clause_article_of_a_named_law():
    text = "theo quy định tại điểm l khoản 1 Điều 2 Luật Thuế tiêu thụ đặc biệt."
    assert find_references(text) == [
        LegalReference("2", "1", "l", law_name="thue tieu thu dac biet")
    ]


def test_article_of_a_numbered_decree():
    assert find_references("khoản 3 Điều 5 Nghị định số 181/2025/NĐ-CP") == [
        LegalReference("5", "3", document_number="181/2025/nd-cp")
    ]


def test_this_document_and_no_target_are_internal():
    references = find_references("khoản 2 Điều này; Điều 7 Nghị định này; khoản 1 Điều 3.")
    assert all(reference.same_document for reference in references)
    assert [reference.article for reference in references] == ["7", "3"]


def test_reference_without_diacritics():
    assert find_references("diem a khoan 2 Dieu 9 Luat so 48/2024/QH15") == [
        LegalReference("9", "2", "a", document_number="48/2024/qh15")
    ]


def test_document_mention_without_article():
    assert find_references("hướng dẫn tại Thông tư số 80/2021/TT-BTC") == [
        LegalReference(None, document_number="80/2021/tt-btc")
    ]


def test_enacting_clause_is_not_a_reference():
    assert find_references("Căn cứ Luật Thuế giá trị gia tăng số 48/2024/QH15;\nĐiều 1") == [
        LegalReference("1", same_document=True)
    ]
