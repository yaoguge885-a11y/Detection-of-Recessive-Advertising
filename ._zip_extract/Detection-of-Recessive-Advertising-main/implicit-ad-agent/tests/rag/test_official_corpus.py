from impad.rag import HybridLegalRetriever, load_legal_corpus
from impad.rag.corpus import build_default_legal_retriever


def test_official_corpus_is_real_versioned_and_traceable():
    corpus = load_legal_corpus()

    assert corpus.corpus_version == "cn-official-v1-2026-07-27"
    assert len(corpus.documents) == 2
    assert all(not item.fixture_only for item in corpus.documents)
    assert all(
        item.source_path_or_url.startswith("https://www.samr.gov.cn/")
        for item in corpus.documents
    )
    assert {
        item.authority_level for item in corpus.documents
    } == {"law", "regulation"}


def test_default_retriever_returns_exact_official_clause_and_abstains():
    retriever = build_default_legal_retriever(minimum_score=0.2)
    assert isinstance(retriever, HybridLegalRetriever)
    evidence = retriever.retrieve(
        "体验分享 消费测评 购物链接 显著标明广告",
        top_k=3,
    )

    assert evidence
    assert any(item.article_id == "第九条" for item in evidence)
    assert all(item.source_id.startswith("samr_") for item in evidence)
    assert evidence[0].rerank_score == 1.0

    strict = build_default_legal_retriever(minimum_score=0.999)
    assert strict.retrieve("篮球天气与旅行摄影", top_k=5) == []
