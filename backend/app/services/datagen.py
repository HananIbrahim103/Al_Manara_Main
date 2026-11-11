"""Test cases written from real open-data tables. Plain code, no LLM.

The model under test gets an excerpt of a published table (Bayanat) and a question about it. The right
answer is computed here from the table, so these cases can fail a check (unlike LLM-written cases).

  lookup   (task_accuracy)  the figure for one row of the excerpt
  total    (task_accuracy)  the sum over one group; the model has to add up
  highest  (task_accuracy)  which category has the largest figure
  absent   (hallucination)  the asked-for row was left out; the model must say it is not in the table
  lookup_ar (arabic_msa)    the lookup, asked in Modern Standard Arabic

Generation is seeded with the snapshot's checksum: the same table always gives the same cases.
"""
import random
import re
from dataclasses import dataclass

from app.services.bayanat import as_number

ORIGIN = "bayanat"
EXCERPT_ROWS = 14
DATA_INSTRUCTION = (
    "\n\nWhen a message includes an official statistics table, answer only from that table. Give exact figures as "
    "they appear or as computed from the table. If the table does not contain what is asked, say clearly that it is "
    "not in the table; never estimate or use outside knowledge.")
_ARABIC = re.compile(r"[؀-ۿ]")
_TOTALS = {"total", "all", "grand total", "المجموع", "الإجمالي", "الاجمالي", "اجمالي", "إجمالي", "المجموع الكلي"}
_COUNTRY = {"uae", "united arab emirates", "الإمارات", "دولة الإمارات"}
_NOT_IN_TABLE = ["not in the table", "not included", "not available", "not provided", "not listed", "does not", "doesn't",
                 "no data", "not shown", "isn't", "cannot", "can't", "غير متوفر", "غير موجود", "لا يتضمن", "لا يحتوي", "ليس"]


@dataclass
class CaseDraft:
    check_key: str
    language: str
    kind: str
    prompt: str
    expected: dict
    answer: str


def _fmt(value: float) -> str:
    return str(int(value)) if float(value).is_integer() else f"{value:.2f}".rstrip("0").rstrip(".")


def _label(value) -> str:
    return _fmt(value) if isinstance(value, float) else str(value)


def _choose_dimensions(rows: list[dict], dimensions: list[str]) -> tuple[str, str | None]:
    """Primary: the dimension with the most categories (2-40). Secondary: another with 2-12 that is not a translation of it."""
    distinct = {d: {r[d] for r in rows if r.get(d) is not None} for d in dimensions}
    usable = [d for d in dimensions if 2 <= len(distinct[d]) <= 40]
    if not usable:
        usable = [d for d in dimensions if len(distinct[d]) >= 2]
    # Prefer English-labelled columns for the main questions when the table has both languages.
    usable.sort(key=lambda d: (any(_ARABIC.search(str(v)) for v in distinct[d]), -len(distinct[d])))
    primary = usable[0]

    def same_thing(a: str, b: str) -> bool:  # Arabic/English twins: one value of a always goes with one value of b
        pairs = {(r.get(a), r.get(b)) for r in rows}
        return len(pairs) <= max(len(distinct[a]), len(distinct[b]))

    secondary = next((d for d in usable[1:] if 2 <= len(distinct[d]) <= 12 and not same_thing(primary, d)), None)
    return primary, secondary


def _group(rows: list[dict], keys: list[str], measure: str) -> dict[tuple, float]:
    totals: dict[tuple, float] = {}
    for row in rows:
        value = as_number(row.get(measure))
        if value is None or any(row.get(k) is None for k in keys):
            continue
        key = tuple(row[k] for k in keys)
        totals[key] = totals.get(key, 0.0) + value
    return totals


def _table_text(keys: list[str], measure: str, lines: list[tuple[tuple, float]]) -> str:
    head = " | ".join(keys + [measure])
    return head + "\n" + "\n".join(" | ".join([_label(v) for v in key] + [_fmt(value)]) for key, value in lines)


def _context(source, keys, lines, arabic=False) -> str:
    if arabic:
        intro = f"الجدول التالي مقتطف من مجموعة بيانات رسمية منشورة على منصة بيانات (bayanat.ae): «{source['title']}» — الجهة: {source['publisher']}."
    else:
        intro = f"The table below is an excerpt of an official dataset published on Bayanat.ae: \"{source['title']}\" ({source['publisher']})."
    return intro + "\n\n" + _table_text(keys, source["measure"], lines)


def without_totals(rows: list[dict], dimensions: list[str]) -> list[dict]:
    """Drop 'Total' / 'المجموع' rows, and a country-wide row next to its emirates, so nothing is counted twice."""
    drop = {d: set(_TOTALS) for d in dimensions}
    for d in dimensions:
        values = {str(r.get(d)).strip().casefold() for r in rows}
        if values & _COUNTRY and len(values - _COUNTRY) >= 2:
            drop[d] |= _COUNTRY
    return [r for r in rows if not any(str(r.get(d)).strip().casefold() in drop[d] for d in dimensions)]


def generate(source: dict, languages: list[str]) -> list[CaseDraft]:
    """`source` needs title, publisher, rows, measure, dimensions, checksum."""
    measure = source["measure"]
    rows = without_totals(source["rows"], source["dimensions"])
    rng = random.Random(source["checksum"])
    percent = bool(re.search(r"percent|%|نسبة|rate|ratio", measure, re.IGNORECASE))
    primary, secondary = _choose_dimensions(rows, source["dimensions"])
    keys = [primary] + ([secondary] if secondary else [])
    if percent:
        # Shares do not add up: every question must point at exactly one published row.
        varying = [d for d in source["dimensions"] if len({r.get(d) for r in rows}) > 1]
        keys = [primary] + [d for d in varying if d != primary and len({(r.get(primary), r.get(d)) for r in rows}) > len({r.get(primary) for r in rows})]
        if len({tuple(r.get(k) for k in keys) for r in rows}) != len(rows):
            return []
    grouped = _group(rows, keys, measure)
    if len(grouped) < 4:
        return []
    items = sorted(grouped.items(), key=lambda kv: [str(x) for x in kv[0]])
    drafts: list[CaseDraft] = []

    def excerpt(must: list[tuple], exclude: tuple | None = None) -> list[tuple[tuple, float]]:
        pool = [kv for kv in items if kv[0] not in must and kv[0] != exclude]
        picked = [kv for kv in items if kv[0] in must] + rng.sample(pool, min(len(pool), EXCERPT_ROWS - len(must)))
        return sorted(picked, key=lambda kv: [str(x) for x in kv[0]])

    def describe(key: tuple, arabic=False) -> str:
        joiner = "، و" if arabic else ", "
        return joiner.join(f"{k} = {_label(v)}" for k, v in zip(keys, key))

    # lookup x2
    for key, value in rng.sample(items, min(2, len(items))):
        lines = excerpt([key])
        prompt = _context(source, keys, lines) + f"\n\nUsing only this table: what is the {measure} where {describe(key)}?"
        drafts.append(CaseDraft("task_accuracy", "en", "lookup", prompt, {"numbers": [_fmt(value)]}, _fmt(value)))

    # total over the secondary dimension (not for percentages, which do not add up)
    if secondary and not percent:
        by_primary: dict = {}
        for key, value in items:
            by_primary.setdefault(key[0], []).append((key, value))
        groups = [g for g in by_primary.values() if 2 <= len(g) <= 10]
        if groups:
            group = rng.choice(groups)
            total = sum(v for _, v in group)
            lines = excerpt([k for k, _ in group])
            prompt = (_context(source, keys, lines) + f"\n\nUsing only this table: what is the total {measure} for "
                      f"{primary} = {_label(group[0][0][0])}, across every {secondary} shown?")
            drafts.append(CaseDraft("task_accuracy", "en", "total", prompt, {"numbers": [_fmt(total)]}, _fmt(total)))

    # highest category of the primary dimension
    primary_totals = sorted(_group(rows, [primary], measure).items(), key=lambda kv: -kv[1])
    if len(primary_totals) >= 3 and primary_totals[0][1] > primary_totals[1][1] and not percent:
        shown = primary_totals[:EXCERPT_ROWS]
        rng.shuffle(shown)
        winner = _label(primary_totals[0][0][0])
        prompt = (_context(source, [primary], shown) + f"\n\nUsing only this table: which {primary} has the highest {measure}? "
                  "Name it and give its figure.")
        drafts.append(CaseDraft("task_accuracy", "en", "highest", prompt,
                                {"must_include": [winner], "numbers": [_fmt(primary_totals[0][1])]}, f"{winner}: {_fmt(primary_totals[0][1])}"))

    # absent row: the asked-for row is left out of the excerpt
    key, value = rng.choice(items)
    lines = excerpt([], exclude=key)
    prompt = _context(source, keys, lines) + f"\n\nUsing only this table: what is the {measure} where {describe(key)}?"
    # The phrase list is loose on purpose (many ways to say it), so the judge also reads the answer against the rubric.
    expected = {"must_include_any": [_NOT_IN_TABLE],
                "rubric": "Says clearly that the table does not contain the row asked for. Gives no figure for that row: "
                          "no estimate, no approximation, no value from outside the table."}
    if len(_fmt(value)) >= 3 and all(_fmt(value) != _fmt(v) for _, v in lines):
        expected["numbers_absent"] = [_fmt(value)]  # the real figure exists on the portal; quoting it means outside knowledge
    drafts.append(CaseDraft("hallucination", "en", "absent", prompt, expected, "Not in the table."))

    # the lookup again, in Modern Standard Arabic
    if "ar-msa" in languages:
        key, value = rng.choice(items)
        lines = excerpt([key])
        prompt = (_context(source, keys, lines, arabic=True)
                  + f"\n\nبالاعتماد على هذا الجدول فقط: ما قيمة «{measure}» عندما {describe(key, arabic=True)}؟ أجب باللغة العربية الفصحى.")
        drafts.append(CaseDraft("arabic_msa", "ar-msa", "lookup_ar", prompt, {"numbers": [_fmt(value)]}, _fmt(value)))
    return drafts
