from db.engine import normalize_url


def test_normalize_url():
    assert normalize_url("postgres://u:p@h/db") == "postgresql+psycopg://u:p@h/db"
    assert normalize_url("postgresql://u:p@h:5432/db") == "postgresql+psycopg://u:p@h:5432/db"
    assert normalize_url("sqlite:///x.db") == "sqlite:///x.db"


def test_migrate_is_idempotent(engine):
    from db.migrate import migrate
    migrate(engine)
    assert migrate(engine) == []


def test_dashboard_base_url_candidates(monkeypatch):
    from api_client import candidate_base_urls
    monkeypatch.delenv("API_BASE_URL", raising=False)
    monkeypatch.delenv("API_HOST", raising=False)
    assert candidate_base_urls() == ["http://localhost:8000"]
    monkeypatch.setenv("API_HOST", "mosje-api-x1")
    assert candidate_base_urls()[0] == "https://mosje-api-x1.onrender.com"
    monkeypatch.setenv("API_BASE_URL", "https://api.example.org/")
    assert candidate_base_urls()[0] == "https://api.example.org"


def test_scenario_table_definition():
    from mosje.scenarios import table_definition
    rows = table_definition()
    assert len(rows) == 59 and sum(r["Reachability"] == "Unreachable" for r in rows) == 27
