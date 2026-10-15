#!/usr/bin/env python3
"""
Fix PGA events filed under the wrong tournament_id (found 2026-10-15
while dating every training event for the date-ordered retrain).

1. Stats filed under the CALENDAR year instead of the SEASON. Fall events
   belong to the next season (R{season}{id}); these four were filed under
   the calendar year, so no season window can date them and the
   date-ordered table dropped them. Each was verified by its winner topping
   SG: Total, and nothing else is filed under the correct id, so moving
   them conflicts with nothing:
     R2020014 -> R2021014  Masters, Nov 2020         (Dustin Johnson, then Im)
     R2020026 -> R2021026  U.S. Open, Sept 2020      (DeChambeau, then Wolff)
     R2019490 -> R2020490  Greenbrier, Sept 2019     (Joaquin Niemann)
     R2020522 -> R2021522  Corales Puntacana, Sept 2020 (Hudson Swafford)
   Five more calendar-labeled events (R2017521, R2019020, R2019527,
   R2019528, R2021478) are NOT moved: a correctly-labeled copy exists with
   DIFFERENT values, so which is right is unknown. They stay undated and
   out of ordering.

2. R2021535 "U.S. Open (2021)" in leaderboards_2021.csv is a row-for-row
   copy of the 2025 U.S. Open (J.J. Spaun, 279; 156/156 positions equal to
   R2025026). Its tournament_stats/form_stats ARE the real 2021 event (Jon
   Rahm, then Oosthuizen, top SG), so only the 156 leaderboard rows go.
   Restoring the real 2021 results from DataGolf is part of roadmap #2.

Idempotent: re-running finds nothing left to change.

Usage:
    python3 scripts/maintenance/fix_mislabeled_events.py            # dry run
    python3 scripts/maintenance/fix_mislabeled_events.py --write
"""
import argparse
import csv
import io
from pathlib import Path

HIST = Path(__file__).resolve().parents[2] / "data" / "historical"
RELABEL = {"R2020014": "R2021014", "R2020026": "R2021026",
           "R2019490": "R2020490", "R2020522": "R2021522"}
BAD_LEADERBOARD = ("leaderboards_2021.csv", "R2021535")


def _rows(path: Path):
    """(header fields, [(raw line, parsed fields)]). Raw lines are kept so
    untouched rows are written back byte-for-byte: rewriting through pandas
    reformatted thousands of unrelated rows (0.000 -> 0.0)."""
    lines = path.read_text().splitlines(keepends=True)
    header = next(csv.reader([lines[0]]))
    return lines[0], header, [(ln, next(csv.reader([ln]))) for ln in lines[1:] if ln.strip()]


def _fmt(fields) -> str:
    buf = io.StringIO()
    csv.writer(buf, lineterminator="\n").writerow(fields)
    return buf.getvalue()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    write = ap.parse_args().write

    for kind in ("tournament_stats", "form_stats"):
        files = sorted(HIST.glob(f"{kind}_20*.csv"))
        parsed = {f: _rows(f) for f in files}
        all_tids = {r[h.index("tournament_id")] for f, (_, h, rows) in parsed.items() for _, r in rows}
        for f, (head_line, header, rows) in parsed.items():
            ti = header.index("tournament_id")
            yi = header.index("year") if "year" in header else None
            out, counts = [head_line], {}
            for raw, r in rows:
                old = r[ti]
                new = RELABEL.get(old)
                if new and new not in all_tids:
                    r = list(r); r[ti] = new
                    if yi is not None:
                        r[yi] = new[1:5]
                    out.append(_fmt(r)); counts[old] = counts.get(old, 0) + 1
                else:
                    if new and new in all_tids and old not in counts:
                        counts[old] = -1
                    out.append(raw)
            for old, n in counts.items():
                if n < 0:
                    print(f"  {kind}: {RELABEL[old]} already exists — NOT moving {old} (would mix two copies)")
                else:
                    print(f"  {kind}/{f.name}: {old} -> {RELABEL[old]} ({n} rows, year -> {RELABEL[old][1:5]})")
            if write and any(n > 0 for n in counts.values()):
                f.write_text("".join(out))

    f = HIST / BAD_LEADERBOARD[0]
    head_line, header, rows = _rows(f)
    ti = header.index("tournament_id")
    keep = [raw for raw, r in rows if r[ti] != BAD_LEADERBOARD[1]]
    dropped = len(rows) - len(keep)
    if dropped:
        print(f"  {f.name}: dropping {dropped} {BAD_LEADERBOARD[1]} rows (a copy of the 2025 U.S. Open)")
        if write:
            f.write_text(head_line + "".join(keep))
    if not write:
        print("(dry run — rerun with --write)")


if __name__ == "__main__":
    main()
