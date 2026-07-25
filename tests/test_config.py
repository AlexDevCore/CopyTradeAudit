from src import config


def test_project_name():
    assert config.PROJECT_NAME == "copytrader"


def test_env_file_exists_false_when_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "ENV_FILE", tmp_path / ".env")
    assert config.env_file_exists() is False


def test_env_file_exists_true_when_present(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text("KEY=value")
    monkeypatch.setattr(config, "ENV_FILE", env_file)
    assert config.env_file_exists() is True


def test_load_environment_false_when_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "ENV_FILE", tmp_path / ".env")
    assert config.load_environment() is False


def test_load_environment_loads_variables(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text("SMOKE_TEST_VAR=hello\n")
    monkeypatch.setattr(config, "ENV_FILE", env_file)
    monkeypatch.delenv("SMOKE_TEST_VAR", raising=False)

    assert config.load_environment() is True
    assert config.get_env("SMOKE_TEST_VAR") == "hello"


def test_get_env_returns_default_when_missing(monkeypatch):
    monkeypatch.delenv("SMOKE_TEST_MISSING", raising=False)
    assert config.get_env("SMOKE_TEST_MISSING", "fallback") == "fallback"
