from src.main import call_claude


def test_call_claude_returns_none_without_api_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert call_claude("hello") is None
