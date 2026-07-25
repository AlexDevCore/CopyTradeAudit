"""Web dashboard smoke tests: all five screens render paper-mode state."""

from fastapi.testclient import TestClient
from src.web.app import create_app
from src.web.demo import build_demo_service

client = TestClient(create_app(build_demo_service()))


def test_all_screens_return_200():
    for path in ("/", "/markets", "/traders", "/portfolio", "/audit"):
        assert client.get(path).status_code == 200


def test_dashboard_shows_paper_badge_and_metrics():
    html = client.get("/").text
    assert ">PAPER</span>" in html  # active mode badge is PAPER
    assert "class='badge LIVE'" not in html  # not rendered as LIVE
    assert "Strategy win rate" in html
    assert "Net result" in html


def test_markets_shows_decisions_including_no_trade():
    html = client.get("/markets").text
    assert "BUY YES" in html
    assert "NO_TRADE" in html  # the longshot gate fires


def test_traders_lists_pool_with_adjusted_win_rate():
    html = client.get("/traders").text
    assert "0x9a1b" in html
    assert "Adj WR" in html


def test_portfolio_shows_hold_to_resolution_column():
    html = client.get("/portfolio").text
    assert "Hold-to-res PnL" in html
    assert "senate-control-dem" in html


def test_audit_shows_events():
    html = client.get("/audit").text
    assert "SIGNAL" in html
    assert "ENTRY" in html
