from ursula.rank import rank, terms, windows

DOC = "\n\n".join(
    [
        "Introduction. "
        + "Irrigation scheduling matters across the Commonwealth. " * 12,
        "Methods. "
        + "We deployed capacitance probes at three depths in each plot. " * 12,
        "Results. The random forest reached an R2 of 0.87 for soil moisture. " * 12,
        "Acknowledgements. "
        + "We thank the field technicians and the funding body. " * 12,
    ]
)


def test_terms_drops_stopwords_and_single_characters():
    assert terms("How does the R2 of a model vary") == ["r2", "model", "vary"]


def test_windows_split_a_long_document():
    assert len(windows(DOC)) > 1
    assert all(w.strip() for w in windows(DOC))


def test_rank_finds_the_section_that_answers_the_question():
    passages = rank(DOC, "random forest R2 accuracy", max_chars=1500)
    assert passages
    assert "random forest" in passages[0].text.lower()


def test_rank_returns_passages_in_document_order():
    passages = rank(DOC, "irrigation random forest technicians", max_chars=6000)
    assert [p.position for p in passages] == sorted(p.position for p in passages)


def test_rank_respects_the_character_budget():
    passages = rank(DOC, "soil moisture", max_chars=900)
    assert sum(len(p.text) for p in passages) <= 900


def test_rank_without_a_question_returns_the_opening():
    passages = rank(DOC, "", max_chars=2000)
    assert passages and passages[0].position == 0


def test_rank_trims_rather_than_returning_nothing():
    passages = rank(DOC, "random forest", max_chars=300)
    assert passages and len(passages[0].text) <= 300


def test_rank_of_empty_text_is_empty():
    assert rank("", "anything") == []
