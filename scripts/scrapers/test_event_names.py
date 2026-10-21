"""Spec for event_names.same_event. Run: python3 scripts/scrapers/test_event_names.py

Every name is real: from our schedules, DataGolf's event list (Oct 21,
2026), or a feed name already in test_event_guard.py (the CJ Cup and
Bermuda variants, the Presidents Cup field from the Bank of Utah bug).
Every DIFFERENT pair is one the old names_match called the same event.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from event_names import same_event  # noqa: E402

# Same tournament, different wording (sponsor suffixes, year tokens, accents).
SAME = [
    ("THE CJ CUP Byron Nelson", "CJ Cup Byron Nelson"),
    ("THE CJ CUP Byron Nelson", "The CJ Cup Byron Nelson"),
    ("Butterfield Bermuda Championship", "Bermuda Championship"),
    ("Open de España", "Open de Espana"),
    ("Open de Espana", "Open de Espana presented by Madrid"),
    ("Abu Dhabi Aldar Championship", "Abu Dhabi Championship"),
    ("Arnold Palmer Invitational", "Arnold Palmer Invitational presented by Mastercard"),
    ("Cognizant Classic", "Cognizant Classic in The Palm Beaches"),
    ("Mexico Open at VidantaWorld", "VidantaWorld Mexico Open"),
    ("The Memorial Tournament", "the Memorial Tournament presented by Workday"),
    ("WM Phoenix Open", "Waste Management Phoenix Open"),
    ("FedEx St. Jude Championship", "FedEx St. Jude Invitational"),
    ("DS Automobiles 83deg Open d'Italia", "DS Automobiles 84deg Open d'Italia"),
    ("Masters Tournament", "The Masters"),
]

# Different tournaments that share a sponsor or a generic word.
DIFFERENT = [
    ("RBC Canadian Open", "RBC Heritage"),
    ("Genesis Scottish Open", "The Genesis Invitational"),
    ("Genesis Championship", "Genesis Scottish Open"),
    ("Genesis Championship", "The Genesis Invitational"),
    ("BMW Championship", "BMW PGA Championship"),
    ("BMW Championship", "BMW International Open"),
    ("BMW International Open", "BMW PGA Championship"),
    ("BMW Australian PGA Championship", "BMW PGA Championship"),
    ("PGA Championship", "BMW PGA Championship"),
    ("PGA Championship", "BMW Australian PGA Championship"),
    ("Masters Tournament", "Qatar Masters"),
    ("The Masters", "Omega European Masters"),
    ("Masters Tournament", "Husqvarna British Masters hosted by Sir Nick Faldo"),
    ("Qatar Masters", "Omega European Masters"),
    ("TOUR Championship", "DP World Tour Championship"),
    ("DP World India Championship", "DP World Tour Championship"),
    ("Open de Espana", "FedEx Open de France"),
    ("Open de Espana", "Open de Portugal | Cascais - Lisboa"),
    ("Bank of Utah Championship", "Deutsche Bank Singapore Open"),
    ("AfrAsia Bank Mauritius Open", "Bank of Utah Championship"),
    ("Alfred Dunhill Championship", "Alfred Dunhill Links Championship"),
    ("Hero Dubai Desert Classic", "Dubai Invitational"),
    ("Hero Indian Open", "Hero World Challenge"),
    ("Hero Dubai Desert Classic", "Hero Indian Open"),
    ("Danish Golf Championship", "Nedbank Golf Challenge in honour of Gary Player"),
    ("Texas Children's Houston Open", "Valero Texas Open"),
    ("Presidents Cup", "Bank of Utah Championship"),
    ("Baycurrent Classic", "Butterfield Bermuda Championship"),
]


def test_same_pairs_match_both_ways():
    bad = [(a, b) for a, b in SAME if not (same_event(a, b) and same_event(b, a))]
    assert not bad, f"should be the same event: {bad}"


def test_different_pairs_refused_both_ways():
    bad = [(a, b) for a, b in DIFFERENT if same_event(a, b) or same_event(b, a)]
    assert not bad, f"should be different events: {bad}"


def test_every_name_matches_itself():
    for a, b in SAME + DIFFERENT:
        assert same_event(a, a) and same_event(b, b), (a, b)


def test_filler_only_names_match_only_themselves():
    # Kept from test_event_guard.py: names_match must not lose these.
    assert same_event("The Open Championship", "The Open Championship")
    assert same_event("U.S. Open", "US Open")
    assert not same_event("The Open Championship", "U.S. Open")
    assert not same_event("The Open", "The Open Championship")


def test_unknown_name_fails_closed():
    assert not same_event("Butterfield Bermuda Championship", "")
    assert not same_event("", "")


def test_guard_uses_same_event_rules():
    from event_guard import names_match

    for a, b in SAME:
        assert names_match(a, b) and names_match(b, a), (a, b)
    for a, b in DIFFERENT:
        assert not names_match(a, b) and not names_match(b, a), (a, b)


if __name__ == "__main__":
    tests = [(n, f) for n, f in list(globals().items()) if n.startswith("test_") and callable(f)]
    passed = 0
    for name, fn in tests:
        try:
            fn()
            passed += 1
            print(f"  ok    {name}")
        except NotImplementedError:
            print(f"  TODO  {name}")
        except AssertionError as e:
            print(f"  FAIL  {name}: {e}")
    print(f"\n{passed}/{len(tests)} passed")
    raise SystemExit(0 if passed == len(tests) else 1)
