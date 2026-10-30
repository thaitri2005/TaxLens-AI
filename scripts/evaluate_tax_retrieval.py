import argparse
import hashlib
import json
import sys
from datetime import date
from pathlib import Path
from typing import Any

from sqlalchemy import func, select

from taxlens.config import get_settings
from taxlens.db import SessionLocal
from taxlens.document_processing.process import CLAUSE_PATTERN
from taxlens.evaluation.corpus_manifest import (
    build_corpus_manifest,
    code_version,
    compare_manifests,
)
from taxlens.evaluation.gold_set import load_gold_set
from taxlens.evaluation.metrics import (
    evaluate_retrieval,
    provision_coverage,
    provision_ranks,
)
from taxlens.evaluation.reports import persist_retrieval_report
from taxlens.evaluation.retrieval_runner import (
    evaluation_status,
    evaluation_status_reason,
    metrics_summary,
)
from taxlens.evaluation.tracking import get_experiment_tracker
from taxlens.legal_data.models import (
    DocumentChunk,
    DocumentEmbedding,
    DocumentVersion,
    LegalDocument,
)
from taxlens.retrieval.embeddings import get_embedding_provider
from taxlens.retrieval.issues import Issue, issue_guided_search
from taxlens.retrieval.search import (
    SearchFilters,
    SearchMode,
    SearchResult,
    hybrid_search_chunks,
    keyword_search_chunks,
    semantic_search_chunks,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate retrieval against labeled tax queries")
    parser.add_argument(
        "--dataset",
        type=Path,
        default=Path("data/evaluation/tax_article_retrieval.json"),
        help="A JSON dataset, or an annotated gold-set CSV such as gold_set_v1.csv",
    )
    parser.add_argument(
        "--verified-only",
        action="store_true",
        help="Gold set only: skip cases marked uncertain or whose source is not verified (N)",
    )
    parser.add_argument(
        "--k",
        type=int,
        default=None,
        help="Evaluate only this K; retained for backwards compatibility",
    )
    parser.add_argument(
        "--ks",
        nargs="+",
        type=int,
        default=[1, 3, 5, 10],
        help="Evaluate one or more K values (default: 1 3 5 10)",
    )
    parser.add_argument(
        "--mode",
        choices=["keyword", "semantic", "hybrid", "issue-guided"],
        default="hybrid",
        help=(
            "Retrieval method to evaluate (default: hybrid). issue-guided interleaves hybrid "
            "searches for the question and each stored issue (--issues)"
        ),
    )
    parser.add_argument(
        "--issues",
        type=Path,
        default=Path("data/evaluation/issues/gold_set_v1.json"),
        help="Stored decompositions for --mode issue-guided (scripts/decompose_issues.py)",
    )
    parser.add_argument(
        "--as-of",
        choices=["none", "case"],
        default="none",
        help=(
            "case: leave out document versions that take effect after each case's "
            "as_of_date (undated versions are kept); none: search the whole corpus"
        ),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Also write the report to this local JSON file",
    )
    parser.add_argument(
        "--corpus-manifest",
        type=Path,
        default=None,
        help="Stop unless the corpus still matches this frozen manifest (freeze_corpus.py)",
    )
    arguments = parser.parse_args()
    ks = [arguments.k] if arguments.k is not None else sorted(set(arguments.ks))
    if any(k < 1 for k in ks):
        parser.error("all K values must be at least 1")

    dataset_bytes = arguments.dataset.read_bytes()
    dataset_hash = hashlib.sha256(dataset_bytes).hexdigest()
    if arguments.dataset.suffix.lower() == ".csv":
        raw_dataset = _gold_set_cases(arguments.dataset, arguments.verified_only)
    else:
        raw_dataset = json.loads(dataset_bytes.decode("utf-8"))
    if not isinstance(raw_dataset, list) or not raw_dataset:
        parser.error("Evaluation dataset must contain at least one case")
    dataset: list[dict[str, Any]] = []
    seen_case_ids: set[str] = set()
    for index, case in enumerate(raw_dataset, start=1):
        if not isinstance(case, dict):
            parser.error(f"Evaluation case {index} must be a JSON object")
        if case.get("answerable") is False:
            # Out-of-corpus cases test answer refusal, not ranking.
            continue
        query = case.get("query")
        relevant_documents = case.get("relevant_document_numbers")
        case_id = case.get("case_id", f"case-{index:03d}")
        if not isinstance(case_id, str) or not case_id.strip():
            parser.error(f"Evaluation case {index} must contain a valid case_id")
        if case_id in seen_case_ids:
            parser.error(f"Evaluation dataset contains duplicate case_id: {case_id}")
        seen_case_ids.add(case_id)
        if not isinstance(query, str) or not query.strip():
            parser.error(f"Evaluation case {index} must contain a non-empty query")
        if not isinstance(relevant_documents, list) or not relevant_documents:
            parser.error(
                f"Evaluation case {index} must contain relevant_document_numbers"
            )
        if not all(isinstance(document_number, str) for document_number in relevant_documents):
            parser.error(
                f"Evaluation case {index} has an invalid relevant document number"
            )
        dataset.append(
            {
                "case_id": case_id,
                "query": query,
                "relevant_document_numbers": relevant_documents,
                "relevant_articles": case.get("relevant_articles") or {},
                "relevant_clauses": case.get("relevant_clauses") or {},
                "essential_provisions": case.get("essential_provisions") or [],
                "supporting_provisions": case.get("supporting_provisions") or [],
                "as_of_date": case.get("as_of_date"),
                "search_date": case.get("search_date") or case.get("as_of_date"),
                "gold_set_fields": {
                    key: case[key] for key in _GOLD_SET_REPORT_FIELDS if key in case
                },
            }
        )
    mode: str = arguments.mode
    issues_by_case = _load_issues(arguments.issues) if mode == "issue-guided" else {}
    if mode == "issue-guided":
        undecomposed = [
            case["case_id"] for case in dataset if case["case_id"] not in issues_by_case
        ]
        if undecomposed:
            parser.error(
                f"No stored issues for {', '.join(undecomposed)}; run scripts/decompose_issues.py"
            )
    provider = get_embedding_provider() if mode != "keyword" else None
    settings = get_settings()
    reports: list[dict[str, Any]] = []
    frozen_corpus: dict[str, Any] | None = None
    primary_k = 5 if 5 in ks else max(ks)
    with SessionLocal() as session:
        expected_document_numbers = {
            document_number
            for case in dataset
            for document_number in case["relevant_document_numbers"]
        }
        corpus_coverage = _corpus_coverage(session, expected_document_numbers)
        corpus_snapshot = _corpus_snapshot(session)
        if arguments.corpus_manifest is not None:
            frozen = json.loads(arguments.corpus_manifest.read_text(encoding="utf-8"))
            difference = compare_manifests(
                frozen,
                build_corpus_manifest(
                    session, settings.embedding_model_id, settings.embedding_model_revision
                ),
            )
            if not difference["unchanged"]:
                print(json.dumps(difference, ensure_ascii=False, indent=2), file=sys.stderr)
                sys.exit(f"The corpus no longer matches {arguments.corpus_manifest}")
            frozen_corpus = {
                "label": frozen.get("label") or str(arguments.corpus_manifest),
                "fingerprint": frozen["fingerprint"],
            }
        embedded_document_numbers = {
            str(item["document_number"])
            for item in corpus_coverage["documents"]
            if item["embedding_count"]
        }
        article_part_counts: dict[tuple[Any, str], int] = {}
        for case in dataset:
            relevant_documents = set(case["relevant_document_numbers"])
            covered_documents = relevant_documents & embedded_document_numbers
            missing_documents = relevant_documents - embedded_document_numbers
            coverage_status = (
                "fully_covered"
                if not missing_documents
                else "partially_covered"
                if covered_documents
                else "not_covered"
            )
            filters = SearchFilters(
                as_of=date.fromisoformat(case["search_date"])
                if arguments.as_of == "case" and case["search_date"]
                else None
            )
            if mode == "issue-guided":
                results = issue_guided_search(
                    session,
                    case["query"],
                    issues_by_case[case["case_id"]],
                    provider,
                    filters,
                    max(ks),
                )
            else:
                results = _search(session, case["query"], provider, mode, filters, max(ks))
            ranked_documents = _unique_document_numbers(results)
            metrics_by_k: dict[str, dict[str, Any]] = {}
            for k in ks:
                metrics = evaluate_retrieval(ranked_documents, relevant_documents, k)
                metrics_by_k[str(k)] = {
                    "hit_at_k": metrics.hit_at_k,
                    "precision_at_k": metrics.precision_at_k,
                    "recall_at_k": metrics.recall_at_k,
                    "reciprocal_rank": metrics.reciprocal_rank,
                    "ndcg_at_k": metrics.ndcg_at_k,
                }
            if case["relevant_articles"]:
                _add_locator_metrics(
                    metrics_by_k,
                    "article",
                    [
                        str(result.chunk.article_number)
                        in case["relevant_articles"].get(result.document.document_number, [])
                        for result in results
                    ],
                )
            if case["relevant_clauses"]:
                _add_locator_metrics(
                    metrics_by_k,
                    "clause",
                    [
                        _clause_hit(
                            result,
                            case["relevant_clauses"].get(result.document.document_number, []),
                        )
                        for result in results
                    ],
                )
            provision_report = _add_provision_metrics(
                metrics_by_k,
                _passage_locators(session, results, article_part_counts),
                case,
                embedded_document_numbers,
            )
            primary_metrics = metrics_by_k[str(primary_k)]
            reports.append(
                {
                    "case_id": case["case_id"],
                    "query": case["query"],
                    "ranked_documents": ranked_documents,
                    "relevant_document_numbers": case["relevant_document_numbers"],
                    **primary_metrics,
                    "metrics_by_k": metrics_by_k,
                    "coverage_status": coverage_status,
                    "covered_relevant_document_numbers": sorted(covered_documents),
                    "missing_relevant_document_numbers": sorted(missing_documents),
                    **provision_report,
                    **case["gold_set_fields"],
                }
            )

    count = len(reports)
    fully_covered_reports = [
        report for report in reports if report["coverage_status"] == "fully_covered"
    ]
    coverage_summary = _coverage_summary(reports, corpus_coverage)
    status = evaluation_status(corpus_coverage)
    metrics_by_k = {str(k): metrics_summary(reports, k) for k in ks}
    for level in ("article", "clause"):
        level_reports = [
            report
            for report in reports
            if f"{level}_hit_at_k" in report["metrics_by_k"][str(ks[0])]
        ]
        if not level_reports:
            continue
        for k in ks:
            level_metrics = [report["metrics_by_k"][str(k)] for report in level_reports]
            metrics_by_k[str(k)][f"mean_{level}_hit_at_k"] = sum(
                bool(item[f"{level}_hit_at_k"]) for item in level_metrics
            ) / len(level_metrics)
            metrics_by_k[str(k)][f"mean_{level}_reciprocal_rank"] = sum(
                float(item[f"{level}_reciprocal_rank"]) for item in level_metrics
            ) / len(level_metrics)
    for k in ks:
        metrics_by_k[str(k)].update(_provision_summary(reports, k))
    fully_covered_metrics_by_k = {
        str(k): metrics_summary(fully_covered_reports, k) for k in ks
    }
    primary_metrics = metrics_by_k[str(primary_k)]
    primary_covered_metrics = fully_covered_metrics_by_k[str(primary_k)]
    output: dict[str, Any] = {
        "model": settings.embedding_model_id,
        "model_revision": settings.embedding_model_revision,
        "retrieval_mode": mode,
        "issues": (
            {"path": str(arguments.issues), "sha256": _file_hash(arguments.issues)}
            if mode == "issue-guided"
            else None
        ),
        "as_of_filter": arguments.as_of,
        "code_version": code_version(),
        "dataset": str(arguments.dataset),
        "dataset_hash": dataset_hash,
        "ks": ks,
        "k": primary_k,
        "case_count": count,
        "evaluation_status": status,
        "quality_gate": {
            "status": status,
            "ranking_metrics_usable": bool(fully_covered_reports),
            "reason": evaluation_status_reason(status),
        },
        "corpus_coverage": corpus_coverage,
        "corpus_snapshot": corpus_snapshot,
        "frozen_corpus": frozen_corpus,
        "metrics_by_k": metrics_by_k,
        "fully_covered_metrics_by_k": fully_covered_metrics_by_k,
        "mean_hit_at_k": primary_metrics["mean_hit_at_k"],
        "mean_precision_at_k": primary_metrics["mean_precision_at_k"],
        "mean_recall_at_k": primary_metrics["mean_recall_at_k"],
        "mean_reciprocal_rank": primary_metrics["mean_reciprocal_rank"],
        "mean_ndcg_at_k": primary_metrics["mean_ndcg_at_k"],
        "fully_covered_case_count": len(fully_covered_reports),
        "fully_covered_mean_hit_at_k": primary_covered_metrics["mean_hit_at_k"],
        "fully_covered_mean_precision_at_k": primary_covered_metrics[
            "mean_precision_at_k"
        ],
        "fully_covered_mean_recall_at_k": primary_covered_metrics["mean_recall_at_k"],
        "fully_covered_mean_reciprocal_rank": primary_covered_metrics[
            "mean_reciprocal_rank"
        ],
        "fully_covered_mean_ndcg_at_k": primary_covered_metrics["mean_ndcg_at_k"],
        "coverage_summary": coverage_summary,
        "cases": reports,
    }
    persisted = persist_retrieval_report(output)
    if arguments.output is not None:
        arguments.output.parent.mkdir(parents=True, exist_ok=True)
        arguments.output.write_text(
            json.dumps(persisted, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    tracker = get_experiment_tracker(settings)
    with tracker.start_run("retrieval-evaluation"):
        tracker.log_params(
            {
                "dataset": str(arguments.dataset),
                "embedding_model": settings.embedding_model_id,
                "retrieval_mode": mode,
                "as_of_filter": arguments.as_of,
                "code_version": code_version() or "unknown",
                "k": primary_k,
                "ks": ",".join(str(k) for k in ks),
                "case_count": count,
                "dataset_hash": dataset_hash,
                "corpus_fingerprint": corpus_snapshot["fingerprint"],
                "frozen_corpus": frozen_corpus["label"] if frozen_corpus else "none",
            }
        )
        tracking_metrics = {
            "mean_hit_at_k": float(persisted["mean_hit_at_k"]),
            "mean_precision_at_k": float(persisted["mean_precision_at_k"]),
            "mean_recall_at_k": float(persisted["mean_recall_at_k"]),
            "mean_reciprocal_rank": float(persisted["mean_reciprocal_rank"]),
            "mean_ndcg_at_k": float(persisted["mean_ndcg_at_k"]),
            "corpus_present_document_count": float(
                corpus_coverage["present_document_count"]
            ),
            "corpus_chunked_document_count": float(
                corpus_coverage["chunked_document_count"]
            ),
            "corpus_embedded_document_count": float(
                corpus_coverage["embedded_document_count"]
            ),
            "corpus_total_document_count": float(
                corpus_snapshot["document_count"]
            ),
            "corpus_total_chunk_count": float(corpus_snapshot["chunk_count"]),
            "corpus_total_embedding_count": float(
                corpus_snapshot["embedding_count"]
            ),
            "document_coverage_rate": float(
                _coverage_summary(reports, corpus_coverage)["document_coverage_rate"]
            ),
            "fully_covered_case_count": float(len(fully_covered_reports)),
        }
        for key in (
            "mean_essential_recall_at_k",
            "essential_full_coverage_rate",
            "mean_essential_in_corpus_recall_at_k",
            "essential_in_corpus_full_coverage_rate",
            "mean_supporting_recall_at_k",
        ):
            if primary_metrics.get(key) is not None:
                tracking_metrics[key] = float(primary_metrics[key])
        if fully_covered_reports:
            tracking_metrics.update(
                {
                    "fully_covered_mean_hit_at_k": float(
                        persisted["fully_covered_mean_hit_at_k"]
                    ),
                    "fully_covered_mean_precision_at_k": float(
                        persisted["fully_covered_mean_precision_at_k"]
                    ),
                    "fully_covered_mean_recall_at_k": float(
                        persisted["fully_covered_mean_recall_at_k"]
                    ),
                    "fully_covered_mean_reciprocal_rank": float(
                        persisted["fully_covered_mean_reciprocal_rank"]
                    ),
                    "fully_covered_mean_ndcg_at_k": float(
                        persisted["fully_covered_mean_ndcg_at_k"]
                    ),
                }
            )
        tracker.log_metrics(tracking_metrics)
    print(json.dumps(persisted, ensure_ascii=False, indent=2))


_GOLD_SET_REPORT_FIELDS = (
    "case_type",
    "as_of_date",
    "filing_date",
    "search_date",
    "uncertain",
    "source_verified",
    "relevant_clauses",
    "essential_provisions",
    "supporting_provisions",
    "supporting_document_numbers",
    "unparsed_provisions",
)


def _gold_set_cases(path: Path, verified_only: bool) -> list[dict[str, Any]]:
    """Gold-set cases in the JSON dataset format, with short numbers completed from the corpus."""

    with SessionLocal() as session:
        corpus_document_numbers = list(session.scalars(select(LegalDocument.document_number)))
    cases = []
    for gold_case in load_gold_set(path):
        # A derived case (source_verified None) has no letter to verify; only an
        # explicit N or an uncertain label keeps a case out.
        if verified_only and (gold_case.uncertain or gold_case.source_verified is False):
            continue
        case = gold_case.to_evaluation_case(corpus_document_numbers)
        # Conditional and false-premise cases have no essential provisions; they test
        # answers, not ranking.
        case["answerable"] = gold_case.answerable
        cases.append(case)
    return cases


def _add_locator_metrics(
    metrics_by_k: dict[str, dict[str, Any]], level: str, hits: list[bool]
) -> None:
    first_rank = next((rank for rank, hit in enumerate(hits, start=1) if hit), None)
    for k, metrics in metrics_by_k.items():
        metrics[f"{level}_hit_at_k"] = any(hits[: int(k)])
        metrics[f"{level}_reciprocal_rank"] = (
            1 / first_rank if first_rank and first_rank <= int(k) else 0.0
        )


def _add_provision_metrics(
    metrics_by_k: dict[str, dict[str, Any]],
    passages: list[tuple[str, str, Any]],
    case: dict[str, Any],
    embedded_document_numbers: set[str],
) -> dict[str, Any]:
    """Essential and supporting provision coverage within each passage budget K.

    A provision whose document is not embedded cannot be retrieved: the source may not
    list it under tax, or may record it wrongly. The raw metrics count it as missed; the
    ``in_corpus`` metrics leave it out, so they measure ranking alone.
    """

    report: dict[str, Any] = {}
    for label in ("essential", "supporting"):
        provisions = case[f"{label}_provisions"]
        if not provisions:
            continue
        ranks = provision_ranks(passages, provisions)
        in_corpus = [
            any(place[0] in embedded_document_numbers for place in places)
            for places in provisions
        ]
        report[f"{label}_provision_ranks"] = [
            {"provision": provision, "rank": rank, "in_corpus": present}
            for provision, rank, present in zip(provisions, ranks, in_corpus, strict=True)
        ]
        in_corpus_ranks = [rank for rank, present in zip(ranks, in_corpus, strict=True) if present]
        for k, metrics in metrics_by_k.items():
            for prefix, selected in ((label, ranks), (f"{label}_in_corpus", in_corpus_ranks)):
                if not selected:
                    continue
                coverage = provision_coverage(selected, int(k))
                metrics[f"{prefix}_recall_at_k"] = coverage.recall_at_k
                metrics[f"{prefix}_full_coverage_at_k"] = coverage.full_coverage_at_k
    return report


def _passage_locators(
    session, results: list[SearchResult], part_counts: dict[tuple[Any, str], int]
) -> list[tuple[str, str, Any]]:
    """``(document, article, clauses)`` of each passage, for provision matching.

    A passage without a clause number is the whole article only when the article is one
    passage. An article split by size alone (often an OCR'd one, whose clause numbers the
    chunker could not see) has parts holding just some clauses: the clauses a part holds
    are the numbers that start a line in its text.
    """

    locators = []
    for result in results:
        chunk = result.chunk
        article = str(chunk.article_number)
        clauses: Any = chunk.clause_number
        if clauses is None and chunk.article_number is not None:
            key = (chunk.document_version_id, chunk.article_number)
            if key not in part_counts:
                part_counts[key] = session.scalar(
                    select(func.count(DocumentChunk.id)).where(
                        DocumentChunk.document_version_id == chunk.document_version_id,
                        DocumentChunk.article_number == chunk.article_number,
                    )
                ) or 0
            if part_counts[key] > 1:
                clauses = frozenset(
                    match.group(1) for match in CLAUSE_PATTERN.finditer(chunk.content)
                )
        locators.append((result.document.document_number, article, clauses))
    return locators


def _provision_summary(reports: list[dict[str, Any]], k: int) -> dict[str, Any]:
    summary: dict[str, Any] = {}
    for prefix in ("essential", "essential_in_corpus", "supporting", "supporting_in_corpus"):
        metrics = [
            report["metrics_by_k"][str(k)]
            for report in reports
            if f"{prefix}_recall_at_k" in report["metrics_by_k"][str(k)]
        ]
        summary[f"{prefix}_case_count"] = len(metrics)
        summary[f"mean_{prefix}_recall_at_k"] = (
            sum(float(item[f"{prefix}_recall_at_k"]) for item in metrics) / len(metrics)
            if metrics
            else None
        )
        if prefix.startswith("essential"):
            summary[f"{prefix}_full_coverage_rate"] = (
                sum(bool(item[f"{prefix}_full_coverage_at_k"]) for item in metrics)
                / len(metrics)
                if metrics
                else None
            )
    summary["essential_not_in_corpus_count"] = sum(
        not item["in_corpus"]
        for report in reports
        for item in report.get("essential_provision_ranks", [])
    )
    return summary


def _clause_hit(result: SearchResult, clauses: list[list[str | None]]) -> bool:
    # A chunk without a clause number holds a whole article (or its introduction), so it
    # contains any clause of that article; a label without a clause needs only the article.
    article = str(result.chunk.article_number)
    clause = result.chunk.clause_number
    return any(
        article == label_article
        and (label_clause is None or clause is None or clause == label_clause)
        for label_article, label_clause in clauses
    )


def _coverage_summary(
    reports: list[dict[str, Any]], corpus_coverage: dict[str, object]
) -> dict[str, object]:
    expected_count = int(corpus_coverage["expected_document_count"])
    embedded_count = int(corpus_coverage["embedded_document_count"])
    return {
        "expected_document_count": expected_count,
        "embedded_document_count": embedded_count,
        "document_coverage_rate": (
            embedded_count / expected_count if expected_count else 0.0
        ),
        "fully_covered_case_count": sum(
            report["coverage_status"] == "fully_covered" for report in reports
        ),
        "partially_covered_case_count": sum(
            report["coverage_status"] == "partially_covered" for report in reports
        ),
        "not_covered_case_count": sum(
            report["coverage_status"] == "not_covered" for report in reports
        ),
    }


def _corpus_snapshot(session) -> dict[str, object]:
    document_numbers = list(
        session.scalars(
            select(LegalDocument.document_number).order_by(LegalDocument.document_number)
        )
    )
    version_rows = session.execute(
        select(LegalDocument.document_number, DocumentVersion.raw_content_hash)
        .join(DocumentVersion, DocumentVersion.document_id == LegalDocument.id)
        .order_by(LegalDocument.document_number, DocumentVersion.raw_content_hash)
    ).all()
    fingerprint_payload = [
        {
            "document_number": document_number,
            "raw_content_hash": raw_content_hash,
        }
        for document_number, raw_content_hash in version_rows
    ]
    fingerprint = hashlib.sha256(
        json.dumps(fingerprint_payload, sort_keys=True, separators=(",", ":")).encode(
            "utf-8"
        )
    ).hexdigest()
    version_count = session.scalar(select(func.count(DocumentVersion.id))) or 0
    chunk_count = session.scalar(select(func.count(DocumentChunk.id))) or 0
    embedding_count = session.scalar(select(func.count(DocumentEmbedding.id))) or 0
    return {
        "document_count": len(document_numbers),
        "version_count": int(version_count),
        "chunk_count": int(chunk_count),
        "embedding_count": int(embedding_count),
        "fingerprint": fingerprint,
    }


def _corpus_coverage(session, expected_document_numbers: set[str]) -> dict[str, object]:
    statuses: list[dict[str, object]] = []
    for document_number in sorted(expected_document_numbers):
        document = session.scalar(
            select(LegalDocument).where(LegalDocument.document_number == document_number)
        )
        if document is None:
            statuses.append(
                {
                    "document_number": document_number,
                    "present": False,
                    "version_count": 0,
                    "chunk_count": 0,
                    "embedding_count": 0,
                }
            )
            continue

        version_count = session.scalar(
            select(func.count(DocumentVersion.id)).where(
                DocumentVersion.document_id == document.id
            )
        ) or 0
        chunk_count = session.scalar(
            select(func.count(DocumentChunk.id))
            .join(DocumentVersion, DocumentChunk.document_version_id == DocumentVersion.id)
            .where(DocumentVersion.document_id == document.id)
        ) or 0
        embedding_count = session.scalar(
            select(func.count(DocumentEmbedding.id))
            .join(DocumentChunk, DocumentEmbedding.document_chunk_id == DocumentChunk.id)
            .join(DocumentVersion, DocumentChunk.document_version_id == DocumentVersion.id)
            .where(DocumentVersion.document_id == document.id)
        ) or 0
        statuses.append(
            {
                "document_number": document_number,
                "present": True,
                "version_count": int(version_count),
                "chunk_count": int(chunk_count),
                "embedding_count": int(embedding_count),
            }
        )

    return {
        "expected_document_count": len(statuses),
        "present_document_count": sum(bool(item["present"]) for item in statuses),
        "chunked_document_count": sum(bool(item["chunk_count"]) for item in statuses),
        "embedded_document_count": sum(bool(item["embedding_count"]) for item in statuses),
        "documents": statuses,
    }


def _load_issues(path: Path) -> dict[str, list[Issue]]:
    stored = json.loads(path.read_text(encoding="utf-8"))
    return {
        case_id: [Issue(issue=item["issue"], query=item["query"]) for item in entry["issues"]]
        for case_id, entry in stored["cases"].items()
    }


def _file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _search(
    session,
    query: str,
    provider,
    mode: SearchMode,
    filters: SearchFilters,
    limit: int,
) -> list[SearchResult]:
    if mode == "keyword":
        return keyword_search_chunks(session, query, filters, limit)
    if provider is None:
        raise RuntimeError(f"Retrieval mode {mode} requires an embedding provider")
    if mode == "semantic":
        query_vector = provider.embed_query(query).vectors[0]
        return semantic_search_chunks(session, query_vector, provider, filters, limit)
    return hybrid_search_chunks(session, query, provider, filters, limit)


def _unique_document_numbers(results: list[SearchResult]) -> list[str]:
    ranked_documents: list[str] = []
    seen: set[str] = set()
    for result in results:
        document_number = result.document.document_number
        if document_number not in seen:
            seen.add(document_number)
            ranked_documents.append(document_number)
    return ranked_documents


if __name__ == "__main__":
    main()
