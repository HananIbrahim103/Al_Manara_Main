"""Client for Bayanat.ae, the official UAE open data portal. No key needed.

How the portal works (checked 10 Nov 2026):
  - A dataset page is /en/Datasets/Dataset-info?id=<dataset token>. The token keeps working when reused.
  - The page lists each resource as JSON in a `data-item` attribute: a resource token (re-issued on every page
    load), names, format, and a stable file link (/File/Get/<GUID> or an old data.bayanat.ae link with GUIDs).
  - The file itself comes from /api/DatasetResources/DownloadSingle?resourceID=<resource token>.
  - The documented developer API (GetDatasetResource) returned nothing for every id tried, so it is not used.

Published files vary: clean tables, tables under banner rows, metadata sheets, transposed tables, PDFs.
`find_table` picks the first sheet that looks like a real table (a text header row, then rows with a number).
"""
import csv
import hashlib
import html
import io
import json
import re
from dataclasses import dataclass, field
from datetime import date, datetime

import httpx

BASE = "https://bayanat.ae"
PORTAL = "bayanat"
TERMS_URL = f"{BASE}/en/Terms-and-conditions"
MAX_ROWS = 600  # rows kept in the snapshot; enough for question generation, small enough for the database
_TIMEOUT = 60.0
_SKIP_RESOURCE = re.compile(r"metadata|dictionary|infographic|meta data", re.IGNORECASE)
_SIDE = re.compile(r"<h6>\s*([^<]+?)\s*</h6>\s*<span>([^<]*)</span>")
_ITEM = re.compile(r"""accordion-item" data-item=(['"])""")
_NUMBER = re.compile(r"^-?\d+(\.\d+)?$")


class BayanatError(Exception):
    """The portal could not be reached, or the dataset has no usable table."""


@dataclass
class Resource:
    token: str
    name: str
    format_id: int | None
    file_ref: str  # stable link to the file: the GUID part identifies this exact file


@dataclass
class DatasetPage:
    token: str
    title: str
    publisher: str
    last_updated: date | None
    topics: list[str]
    page_url: str
    resources: list[Resource]


@dataclass
class Table:
    columns: list[str]
    rows: list[dict]
    measure: str  # the numeric column questions are asked about
    dimensions: list[str]  # the columns that describe a row
    sheet: str = ""
    total_rows: int = 0


@dataclass
class Snapshot:
    page: DatasetPage
    resource: Resource
    table: Table
    checksum: str
    fetched_at: datetime = field(default_factory=datetime.utcnow)


def page_url(token: str) -> str:
    return f"{BASE}/en/Datasets/Dataset-info?id={token}"


def token_from(value: str) -> str:
    """Accept a dataset token or a full dataset page URL."""
    match = re.search(r"[?&]id=([A-Za-z0-9_-]+)", value)
    return match.group(1) if match else value.strip()


# ───────────── reading the dataset page ─────────────

def parse_page(token: str, text: str) -> DatasetPage:
    title = re.search(r"<h1>\s*([^<]+?)\s*</h1>", text)
    if title is None:
        raise BayanatError("No dataset on this page; check the dataset id.")
    side = {k.strip(): html.unescape(v.strip()) for k, v in _SIDE.findall(text)}
    updated = None
    if re.match(r"\d{2}/\d{2}/\d{4}$", side.get("Last Updated Date", "")):
        updated = datetime.strptime(side["Last Updated Date"], "%d/%m/%Y").date()
    topics = [html.unescape(t.strip()) for t in re.findall(r'<div class="tag-box">\s*<img[^>]*>\s*<span>([^<]+)</span>', text)]
    resources = []
    for match in _ITEM.finditer(text):
        if match.group(1) == '"':
            raw = json.loads(html.unescape(text[match.end():text.index('"', match.end())]))
        else:  # single-quoted attribute: the JSON may itself contain quotes, so decode it as JSON directly
            raw = json.JSONDecoder().raw_decode(text, match.end())[0]
        resources.append(Resource(token=raw["ID"], name=(raw.get("NameEN") or "").strip(), format_id=raw.get("FormatID"),
                                  file_ref=raw.get("FileURL") or f"file:{raw.get('FileID')}"))
    return DatasetPage(token=token, title=html.unescape(title.group(1)), publisher=side.get("Entity Name", ""),
                       last_updated=updated, topics=topics, page_url=page_url(token), resources=resources)


async def fetch_page(client: httpx.AsyncClient, token: str) -> DatasetPage:
    try:
        response = await client.get(page_url(token))
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise BayanatError(f"Could not reach Bayanat: {exc!r}") from exc
    return parse_page(token, response.text)


async def download(client: httpx.AsyncClient, resource: Resource) -> bytes:
    try:
        response = await client.get(f"{BASE}/api/DatasetResources/DownloadSingle",
                                    params={"resourceID": resource.token, "fileName": resource.name or "file"})
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise BayanatError(f"Could not download '{resource.name}': {exc!r}") from exc
    return response.content


# ───────────── finding the table inside a file ─────────────

def _clean(value):
    if value is None:
        return None
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, (int, float)):
        return value
    text = re.sub(r"\s+", " ", str(value)).strip()
    return text or None


def as_number(value) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        text = value.replace(",", "").replace("%", "").strip()
        if _NUMBER.match(text):
            return float(text)
    return None


def _grids(content: bytes) -> list[tuple[str, list[list]]]:
    """Every sheet (or the one CSV) as a list of rows."""
    if content[:2] == b"PK":
        import openpyxl
        book = openpyxl.load_workbook(io.BytesIO(content), read_only=True, data_only=True)
        return [(sheet.title, [[_clean(v) for v in row] for row in sheet.iter_rows(values_only=True)]) for sheet in book.worksheets]
    if content[:5] == b"%PDF-":
        return []
    text = content.decode("utf-8-sig", errors="replace")
    return [("csv", [[_clean(v) for v in row] for row in csv.reader(io.StringIO(text))])]


def _table_in(name: str, grid: list[list]) -> Table | None:
    rows = [r for r in grid if any(v is not None for v in r)]
    for start in range(min(len(rows), 15)):
        header = rows[start]
        cells = [(i, v) for i, v in enumerate(header) if v is not None]
        if len(cells) < 2 or any(as_number(v) is not None for _, v in cells):
            continue
        body = rows[start + 1:]
        width = [i for i, _ in cells]
        sample = body[:5]
        if len(sample) < 2 or not all(any(as_number(r[i] if i < len(r) else None) is not None for i in width) for r in sample):
            continue
        columns, seen = [], set()
        for i, value in cells:
            label = str(value)
            while label in seen:
                label += "_"
            seen.add(label)
            columns.append(label)
        records = []
        for r in body:
            record = {col: (r[i] if i < len(r) else None) for col, (i, _) in zip(columns, cells)}
            if sum(v is not None for v in record.values()) >= 2:
                records.append(record)
        numeric = [c for c in columns if sum(as_number(rec[c]) is not None for rec in records) >= 0.9 * len(records)]
        # The measure is the last mostly-numeric column that is not a year, code or coordinate.
        candidates = [c for c in numeric if not re.search(r"year|سنة|code|lat|long|coordinat|الرمز", c, re.IGNORECASE)]
        if not candidates or len(records) < 3:
            continue
        measure = candidates[-1]
        dimensions = [c for c in columns if c != measure and not re.search(r"lat|long|coordinat|code", c, re.IGNORECASE)
                      and len({rec[c] for rec in records}) > 1]
        if not dimensions:
            continue
        return Table(columns=columns, rows=records[:MAX_ROWS], measure=measure, dimensions=dimensions, sheet=name,
                     total_rows=len(records))
    return None


def find_table(content: bytes) -> Table | None:
    tables = [t for name, grid in _grids(content) if (t := _table_in(name, grid))]
    return max(tables, key=lambda t: t.total_rows) if tables else None


def checksum(table: Table) -> str:
    body = json.dumps({"columns": table.columns, "rows": table.rows}, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(body.encode()).hexdigest()


# ───────────── one call: page, best resource, table ─────────────

async def snapshot(token: str, client: httpx.AsyncClient | None = None) -> Snapshot:
    """Fetch a dataset and return its first usable table. Raises BayanatError when there is none."""
    own = client is None
    client = client or httpx.AsyncClient(timeout=_TIMEOUT, follow_redirects=True, headers={"User-Agent": "tdra-governance-prototype"})
    try:
        page = await fetch_page(client, token_from(token))
        ordered = sorted(page.resources, key=lambda r: bool(_SKIP_RESOURCE.search(r.name)))
        problems = []
        for resource in ordered:
            if _SKIP_RESOURCE.search(resource.name):
                continue
            try:
                table = find_table(await download(client, resource))
            except BayanatError as exc:
                problems.append(str(exc))
                continue
            except Exception as exc:  # an unreadable file: try the next resource
                problems.append(f"'{resource.name}': {exc!r}")
                continue
            if table:
                return Snapshot(page=page, resource=resource, table=table, checksum=checksum(table))
        raise BayanatError(f"No usable table in '{page.title}'. " + "; ".join(problems))
    finally:
        if own:
            await client.aclose()
