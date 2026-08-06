#!/usr/bin/env python3
"""Build a compact preconteo ReleaseView the web fixture adapter can serve.

Source: the full 172MB candidate api-snapshot (real per-mesa preconteo).
Output: a small JSON with the real national summary + 34 department rollups
(aggregated up the geography tree) + datasets. Labelled preliminary preconteo,
NOT synthetic and NOT a certified-tally release.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "data/releases/candidate-2026-r2-dacb28aa766eec87/api-snapshot.json"
OUT = ROOT / "data/fixtures/preliminary-release.json"

d = json.loads(SRC.read_text())
geos = {g["id"]: g for g in d["geographies"]}


def department_of(geo_id):
    g = geos.get(geo_id)
    while g and g.get("level") != "department":
        g = geos.get(g.get("parent_id"))
    return g


# Roll mesa facts up to departments.
dept = {}
mesa_count = {}
for r in d["results"]:
    if r.get("geography_level") != "mesa":
        continue
    dg = department_of(r["geography_id"])
    if not dg:
        continue
    did = dg["id"]
    acc = dept.setdefault(
        did,
        {
            "id": did,
            "code": dg.get("code"),
            "name": dg.get("name"),
            "valid_votes": 0,
            "candidates": {},
        },
    )
    vv = r.get("valid_votes", {})
    if vv.get("status") == "observed" and vv.get("value") is not None:
        acc["valid_votes"] += vv["value"]
    for c in r.get("candidates", []):
        v = c.get("votes", {})
        if v.get("status") == "observed" and v.get("value") is not None:
            acc["candidates"][c["candidate_id"]] = (
                acc["candidates"].get(c["candidate_id"], 0) + v["value"]
            )
    mesa_count[did] = mesa_count.get(did, 0) + 1

department_rollup = []
for did, acc in sorted(dept.items(), key=lambda kv: -kv[1]["valid_votes"]):
    acc["mesas_reported"] = mesa_count.get(did, 0)
    department_rollup.append(acc)

# One real mesa, shown in #mesa as a concrete per-table example (no invented
# dispute — the pre-count tally as published). Pick a mesa with a clean
# observed split for both candidates.
CAND_IDS = [c["candidate"]["id"] for c in d["summary"]["candidates"]]
sample_mesa = None
for r in d["results"]:
    if r.get("geography_level") != "mesa":
        continue
    votes = {c["candidate_id"]: c["votes"].get("value") for c in r.get("candidates", [])
             if c["votes"].get("status") == "observed"}
    vv = r.get("valid_votes", {})
    if len(votes) >= 2 and all(votes.get(cid) for cid in CAND_IDS) and vv.get("value"):
        dg = department_of(r["geography_id"])
        sample_mesa = {
            "mesa_id": r.get("mesa_id"),
            "department": dg.get("name") if dg else None,
            "valid_votes": vv["value"],
            # valid_votes INCLUDES blank ballots (valid = Σcandidates + blank),
            # so the figure needs blanks explicitly or it draws them as votes.
            "blank_votes": (r.get("blank_votes") or {}).get("value") or 0,
            "candidates": {cid: votes.get(cid, 0) for cid in CAND_IDS},
        }
        break

# Keep national + department geographies only (small).
kept_geos = [g for g in d["geographies"] if g.get("level") in ("national", "department")]

compact = {
    "fixture_notice": {
        "es": "Cifras del preconteo oficial de la Registraduria para la segunda vuelta presidencial de 2026.",
        "en": "Figures from the Registraduria's official pre-count for the 2026 presidential runoff.",
    },
    "release": {
        "release_id": d["release"]["release_id"],
        "data_version": d["release"]["data_version"],
        "status": "candidate",
        "synthetic": False,
        "created_at": d["release"]["created_at"],
        "methodology_version": d["release"].get("methodology_version", "audit-priority-v1.0.0"),
    },
    "election": d["election"],
    "provenance": d["provenance"],
    "summary": d["summary"],
    "geographies": kept_geos,
    "mesas": [],
    "results": [r for r in d["results"] if r.get("geography_level") in ("national", "department")],
    "result_page": {"next_cursor": None, "has_more": False, "limit": 50},
    "bulletins": [],
    "evidence": [],
    "comparisons": {},
    "review_signals": [],
    "review_page": {"next_cursor": None, "has_more": False, "limit": 50},
    "datasets": d.get("datasets", []),
    "department_rollup": department_rollup,
    "sample_mesa": sample_mesa,
}

OUT.write_text(json.dumps(compact, ensure_ascii=False))
size_kb = OUT.stat().st_size / 1024
print(f"wrote {OUT} ({size_kb:.0f} KB)")
print(f"departments: {len(department_rollup)}")
print(f"national valid_votes: {compact['summary']['valid_votes']['value']:,}")
for c in compact["summary"]["candidates"]:
    print(
        f"  {c['candidate']['name']['es'][:40]:40} {c['votes']['value']:>12,}  "
        f"{(c['share'] or 0)*100:.2f}%"
    )
top = department_rollup[0]
print(f"top dept: {top['name']} valid={top['valid_votes']:,} mesas={top['mesas_reported']}")
