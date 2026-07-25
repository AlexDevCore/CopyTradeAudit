"""Deterministic replay test: same fixed input -> identical output."""

import json
from pathlib import Path

from src.domain.models import Side
from src.replay.runner import run_replay

FIXTURE = Path(__file__).parent / "fixtures" / "replay_basic.json"


def _load():
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    outcomes = {k: Side(v) for k, v in data["outcomes"].items()}
    return data["trades"], outcomes, data["categories"]


def test_replay_is_deterministic():
    trades, outcomes, categories = _load()
    first = run_replay(trades, outcomes, category_of=categories)
    second = run_replay(trades, outcomes, category_of=categories)
    assert first.as_rows() == second.as_rows()
    assert first.total_decisions == second.total_decisions


def test_replay_counts_and_ranks():
    trades, outcomes, categories = _load()
    result = run_replay(trades, outcomes, category_of=categories)

    # 0xA opened 3 decisions (m1 two same-dir buys = ONE), 0xB opened 2 -> 5 total.
    assert result.total_decisions == 5

    by_wallet = {s.wallet: s for s in result.scores}
    # 0xA: m1 YES (win), m2 NO (win), m3 YES vs NO (loss) -> 2/3
    assert (by_wallet["0xA"].wins, by_wallet["0xA"].losses) == (2, 1)
    # 0xB: m1 NO vs YES (loss), m2 YES vs NO (loss) -> 0/2
    assert (by_wallet["0xB"].wins, by_wallet["0xB"].losses) == (0, 2)

    # Stronger trader ranks first.
    assert result.scores[0].wallet == "0xA"


def test_replay_scores_are_per_category():
    trades, outcomes, categories = _load()
    result = run_replay(trades, outcomes, category_of=categories)
    assert all(s.category == "politics" for s in result.scores)
