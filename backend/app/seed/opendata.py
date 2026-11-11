"""Real open-data tables from Bayanat.ae linked to the seeded Use-Case Cards.

The tables are stored as a snapshot (opendata_snapshot.json) so the seed and the tests never need the network.
Refresh the snapshot from the live portal with:

    python -m app.seed.opendata
"""
import asyncio
import json
from datetime import date
from pathlib import Path

SNAPSHOT = Path(__file__).with_name("opendata_snapshot.json")

# (key, Bayanat dataset id, use cases that rely on it, why)
SOURCES = [
    ("TRF-ACCIDENT-TYPE", "etqZMn7y7Auis-AAbaJdnIfHK7HDLCzII6Wef_pDPP0", ["TRF-ASSIST"],
     "Citizens ask the fines assistant about road-safety statistics."),
    ("TRF-ACCIDENT-CAUSE", "8-DSrAf7YtRVmbvBi8zJg9wFEjqlxkkjkFyuUWG-lFU", ["TRF-ASSIST"],
     "Accident causes, labelled in Arabic: tests reading Arabic tables."),
    ("SCS-MARRIAGE-GRANT", "DdpkeRvedf-5AYJnP5jSuVr3cVkDUGpZyH3DD_WR7XI", ["SCS-ASSIST"],
     "Marriage grant figures by emirate and education, for the benefits assistant."),
    ("SCS-BIRTHS", "BV3WOkwugEzsNYNGW2MskAmee8bdg6NU2imu9kfyghU", ["SCS-ASSIST"],
     "Births by emirate, citizenship and gender, for the civil documents assistant."),
    ("RID-AFFIDAVITS", "0_vu4TR8qGVnnWJM6YHhdqIwmXl33Co4eFY_K_bqYW0", ["RID-SUMM"],
     "Affidavits and authentications by court and type: documents that appear in residency files."),
    ("HRL-FEDERAL-EMPLOYEES", "h6KG3qyneHJZmkSbm1sHhRAJ5p0ynZqFDwTKTlqDqxM", ["HRL-SUMM"],
     "Federal government employees by job category and gender, for HR summaries."),
    ("HRL-LABOUR-FORCE-AD", "btdUv4TxQzMwzwZflOY3uDtEfbRgkNphyyCWHPMrlk8", ["HRL-SUMM"],
     "Labour-force shares (percentages): questions must point at one published row."),
]


def load() -> dict:
    """key -> stored snapshot fields."""
    data = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    for item in data.values():
        if item.get("last_updated"):
            item["last_updated"] = date.fromisoformat(item["last_updated"])
    return data


async def _fetch_all() -> dict:
    from app.services import bayanat

    out = {}
    for key, token, _, _ in SOURCES:
        snap = await bayanat.snapshot(token)
        out[key] = {
            "portal_token": snap.page.token, "title": snap.page.title, "publisher": snap.page.publisher, "topics": snap.page.topics,
            "page_url": snap.page.page_url, "licence_url": bayanat.TERMS_URL,
            "last_updated": snap.page.last_updated.isoformat() if snap.page.last_updated else None,
            "resource_name": snap.resource.name, "file_ref": snap.resource.file_ref, "columns": snap.table.columns,
            "measure": snap.table.measure, "dimensions": snap.table.dimensions, "rows": snap.table.rows,
            "total_rows": snap.table.total_rows, "checksum": snap.checksum, "fetched_at": snap.fetched_at.isoformat() + "Z",
        }
        print(f"{key}: {snap.page.title} ({snap.page.publisher}), {snap.table.total_rows} rows, updated {snap.page.last_updated}")
    return out


if __name__ == "__main__":
    SNAPSHOT.write_text(json.dumps(asyncio.run(_fetch_all()), ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    print(f"Saved {SNAPSHOT}")
