"""Agent 2, evidence half: turn provider documents into one schema and flag the gaps.

The LLM does one thing only: find where a document talks about each field and quote it.
Everything that decides trust is plain code:
  - the quote must really be in the document, or the extraction is thrown away;
  - the status (verified / claimed / unsupported) comes from the kind of document, not from the model;
  - units and scales are normalised by code;
  - any field no document covers is recorded as missing, and missing is treated as a risk.
"""
import re
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import catalog
from app.llm import LLMFailure, call_json
from app.models import ModelVersion, ProviderEvidence

_STATUS_RANK = {"missing": 0, "unsupported": 1, "claimed": 2, "verified": 3}
GAP_STATUSES = ("missing", "unsupported")

# Fields whose absence matters most, and what the risk is in plain words.
GAP_RISK = {
    "data_residency": "It is unknown where data is processed, so data-residency rules cannot be shown to be met.",
    "data_retention": "It is unknown whether the provider keeps the data or trains on it.",
    "licence_terms": "The terms of use and liability are unknown.",
    "safety_evaluation": "There is no evidence the provider tested the model against misuse or prompt injection.",
    "fairness_evaluation": "There is no evidence the provider tested for unequal treatment of groups such as nationalities.",
    "benchmark_arabic": "There is no supported evidence of Arabic performance; our own Arabic tests carry the full weight.",
    "benchmark_general": "Performance claims cannot be relied on; our own tests carry the full weight.",
    "update_policy": "The model may change or be withdrawn without notice.",
    "version_pinning": "It is unknown whether the approved version can be kept in use.",
    "exit_terms": "It is unknown how the department could leave this provider or get its data out.",
    "incident_disclosure": "The provider has not committed to telling us about incidents.",
    "security_certifications": "There is no independent evidence of the provider's security controls.",
    "training_data_summary": "The origin of the training data is unknown.",
    "pricing": "Running cost cannot be estimated.",
    "model_card": "There is no basic description of the model and its limits.",
    "intended_use": "The provider has not said what the model is and is not meant for.",
}
CRITICAL_FIELDS = {"data_residency", "data_retention", "licence_terms", "safety_evaluation", "fairness_evaluation"}

# What to pull out of each field, when the document states it.
ATTRIBUTE_HINTS = {
    "benchmark_general": "metric (string), score (number), scale (e.g. '0-100', '0-1', 'percent'), method_disclosed (bool)",
    "benchmark_arabic": "metric, score, scale, method_disclosed (bool), dialects_covered (list, e.g. ['MSA','Gulf'])",
    "data_residency": "regions (list), in_country_option (bool), contractual_commitment (bool)",
    "data_retention": "retention_days (number), used_for_training (bool), zero_retention_option (bool)",
    "update_policy": "notice_days_major (number), notice_days_minor (number), silent_minor_updates (bool), deprecation_notice_days (number)",
    "version_pinning": "pinning_available (bool), pinned_lifetime_months (number)",
    "pricing": "input_per_million_usd (number), output_per_million_usd (number)",
    "licence_terms": "type (string), government_use (bool), liability_cap (string)",
    "security_certifications": "certifications (list of strings)",
    "exit_terms": "data_export (bool), termination_notice_days (number)",
    "incident_disclosure": "notify_within_hours (number)",
    "safety_evaluation": "red_team (bool), prompt_injection_tested (bool)",
    "fairness_evaluation": "groups_tested (list), nationality_tested (bool)",
}


class ProviderDocument(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    kind: str = Field(description="one of catalog.DOCUMENT_KINDS")
    text: str = Field(min_length=1, max_length=40000)


class ExtractedField(BaseModel):
    field: str
    quote: str = Field(description="the exact sentence(s) copied from the document")
    summary: str = Field(description="one plain sentence saying what the document states")
    attributes: dict[str, Any] = Field(default_factory=dict)


class Extraction(BaseModel):
    fields: list[ExtractedField] = Field(default_factory=list)


def _squash(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


# ---------- trust rules (plain code) ----------

def classify(field: str, kind: str, attributes: dict) -> tuple[str, str]:
    """Status from the kind of document. Returns (status, why)."""
    weight = catalog.DOCUMENT_KINDS.get(kind, "statement")
    is_benchmark = field.startswith("benchmark_")
    if weight == "artefact":
        if is_benchmark and attributes.get("method_disclosed") is False:
            return "claimed", "Stated in a report, but the test method is not disclosed."
        return "verified", f"Backed by a checkable document ({kind.replace('_', ' ')})."
    if kind == "model_card" and field in ("model_card", "intended_use"):
        return "verified", "The model card is itself the evidence for this field."
    if weight == "promotion":
        if is_benchmark or field in ("safety_evaluation", "fairness_evaluation"):
            return "unsupported", f"Only stated in promotional material ({kind.replace('_', ' ')}) with no method or results."
        return "claimed", f"Only stated in promotional material ({kind.replace('_', ' ')}); not a commitment."
    if is_benchmark and attributes.get("method_disclosed") is False:
        return "unsupported", "Benchmark claim with no disclosed method."
    return "claimed", f"Provider statement ({kind.replace('_', ' ')}) with no supporting artefact."


def normalise(field: str, attributes: dict) -> dict:
    """Put provider numbers on one scale so models can be compared."""
    attrs = dict(attributes)
    if field.startswith("benchmark_") and isinstance(attrs.get("score"), (int, float)):
        scale = str(attrs.get("scale", "")).replace(" ", "").lower()
        score = float(attrs["score"])
        if scale in ("0-1", "0–1") or (not scale and score <= 1):
            attrs["score_0_100"] = round(score * 100, 1)
        elif scale in ("0-100", "percent", "%", "") and score <= 100:
            attrs["score_0_100"] = round(score, 1)
        else:
            attrs["score_0_100"] = None  # unknown scale: not comparable, left for a human
    return attrs


# ---------- extraction: LLM, or keyword fallback in mock mode ----------

_KEYWORDS = {
    "model_card": ["model card", "system card", "context window", "parameters"],
    "intended_use": ["intended use", "intended for", "not intended", "must not be used"],
    "licence_terms": ["licence", "license", "terms of service", "liability"],
    "benchmark_arabic": ["arabic"],
    "benchmark_general": ["benchmark", "leaderboard", "scores "],
    "safety_evaluation": ["red team", "red-team", "safety evaluation", "prompt injection"],
    "fairness_evaluation": ["fairness", "bias"],
    "training_data_summary": ["training data", "trained on", "cut-off", "cutoff"],
    "update_policy": ["deprecat", "days' notice", "days notice", "update policy"],
    "version_pinning": ["pinning", "pinned", "snapshot"],
    "data_residency": ["data residency", "processed in", "hosted in", "in-country", "region"],
    "data_retention": ["retention", "retain", "train on customer", "training on customer"],
    "security_certifications": ["iso 27001", "soc 2", "certified"],
    "pricing": ["per million", "pricing", "price"],
    "exit_terms": ["termination", "export", "portability"],
    "incident_disclosure": ["incident", "breach", "notify"],
}


def _keyword_extract(document: ProviderDocument) -> Extraction:
    """Deterministic stand-in for the LLM: first sentence that mentions each field."""
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+|\n+", document.text) if s.strip()]
    found = []
    for field, keywords in _KEYWORDS.items():
        for sentence in sentences:
            lowered = sentence.lower()
            if not any(k in lowered for k in keywords):
                continue
            if field == "benchmark_arabic" and not re.search(r"\d", sentence):
                continue
            attributes: dict[str, Any] = {}
            if field.startswith("benchmark_"):
                number = re.search(r"(\d+(?:\.\d+)?)\s*(%|/\s*100|out of 100)?", sentence)
                if number:
                    attributes = {"score": float(number.group(1)), "scale": "percent" if number.group(2) else "",
                                  "method_disclosed": "method" in lowered and "not" not in lowered}
            if field == "data_residency":
                attributes = {"in_country_option": "uae" in lowered or "in-country" in lowered,
                              "contractual_commitment": "contract" in lowered}
            found.append(ExtractedField(field=field, quote=sentence, summary=sentence, attributes=attributes))
            break
    return Extraction(fields=found)


async def _extract(document: ProviderDocument, model_label: str) -> Extraction:
    field_list = "\n".join(
        f"- {key}: {title}" + (f". Attributes if stated: {ATTRIBUTE_HINTS[key]}" if key in ATTRIBUTE_HINTS else "")
        for key, title in catalog.EVIDENCE_FIELDS.items())
    system = (
        "You read one provider document about an AI model and report what it states for each field below. "
        "Only include a field when the document really states something about it. For each one give: the field key, "
        "`quote` copied exactly from the document, a one-sentence `summary`, and `attributes` with only the values "
        "the document states. Never infer, never fill gaps, never use outside knowledge.\n\nFields:\n" + field_list)
    user = f"Model: {model_label}\nDocument title: {document.title}\nDocument kind: {document.kind}\n\n---\n{document.text}"
    return await call_json(agent="evidence_registry", step="extract_provider_document", system=system, user=user,
                           schema=Extraction, mock=lambda: _keyword_extract(document),
                           log_input={"model": model_label, "title": document.title, "kind": document.kind,
                                      "text": document.text[:12000]})


# ---------- normalise a submission ----------

async def normalise_documents(session: AsyncSession, version: ModelVersion, model_label: str,
                              documents: list[ProviderDocument]) -> dict:
    """Read the documents, update the version's evidence rows, return what changed and what is still missing."""
    best: dict[str, dict] = {}
    discarded, failed_documents = [], []
    for document in documents:
        try:
            extraction = await _extract(document, model_label)
        except LLMFailure as exc:
            failed_documents.append({"title": document.title, "error": str(exc)})
            continue
        haystack = _squash(document.text)
        for item in extraction.fields:
            if item.field not in catalog.EVIDENCE_FIELDS:
                discarded.append({"document": document.title, "field": item.field, "reason": "Not a field in the standard format."})
                continue
            if not item.quote.strip() or _squash(item.quote) not in haystack:
                discarded.append({"document": document.title, "field": item.field,
                                  "reason": "The quoted text is not in the document, so the extraction was not trusted."})
                continue
            attributes = normalise(item.field, item.attributes)
            status, why = classify(item.field, document.kind, attributes)
            candidate = {"status": status, "value": {"summary": item.summary, **attributes, "quote": item.quote},
                         "source": document.title, "note": why}
            current = best.get(item.field)
            if current is None or _STATUS_RANK[status] > _STATUS_RANK[current["status"]]:
                best[item.field] = candidate

    rows = {row.field: row for row in (await session.execute(
        select(ProviderEvidence).where(ProviderEvidence.model_version_id == version.id))).scalars().all()}
    changes, kept = [], []
    for field in catalog.EVIDENCE_FIELDS:
        row = rows.get(field)
        if row is None:
            row = ProviderEvidence(model_version_id=version.id, field=field, status="missing", value={}, source="",
                                   note="Provider supplied nothing for this field. Unknown is treated as a risk.")
            session.add(row)
            rows[field] = row
        new = best.get(field)
        # A document can add or strengthen evidence; it never weakens what is already on file, and a document of
        # the same weight does not silently replace it either: that is reported, and a named person decides (PUT).
        if new and _STATUS_RANK[new["status"]] > _STATUS_RANK[row.status]:
            changes.append({"field": field, "from": row.status, "to": new["status"], "source": new["source"]})
            row.status, row.value, row.source, row.note = new["status"], new["value"], new["source"], new["note"]
        elif new and new["status"] == row.status and new["source"] != row.source:
            kept.append({"field": field, "status": row.status, "on_file_from": row.source, "not_applied_from": new["source"],
                         "reason": "Same weight as the evidence on file. To replace it, a reviewer sets the field after checking both."})
    await session.flush()
    return {"changes": changes, "kept_existing": kept, "discarded_extractions": discarded, "failed_documents": failed_documents,
            "summary": summarise(list(rows.values()))}


def summarise(rows: list[ProviderEvidence], risk_tier: str | None = None) -> dict:
    """Counts by status and the list of gaps, each with its risk in plain words."""
    counts = {status: 0 for status in catalog.EVIDENCE_STATUSES}
    gaps = []
    for row in sorted(rows, key=lambda r: list(catalog.EVIDENCE_FIELDS).index(r.field)):
        counts[row.status] += 1
        if row.status in GAP_STATUSES:
            critical = row.field in CRITICAL_FIELDS
            if risk_tier in ("high", "critical"):
                severity = "high" if critical else "medium"
            else:
                severity = "medium" if critical else "low"
            gaps.append({"field": row.field, "title": catalog.EVIDENCE_FIELDS[row.field], "status": row.status,
                         "severity": severity, "risk": GAP_RISK[row.field], "note": row.note})
    return {"counts": counts, "gaps": gaps,
            "claimed_only": [row.field for row in rows if row.status == "claimed"]}
