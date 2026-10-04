from sqlalchemy import create_engine, inspect

from app.database import Base
import app.models  # noqa: F401


def test_core_tables_are_registered() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    tables = set(inspect(engine).get_table_names())

    expected = {
        "accounts",
        "sources",
        "documents",
        "claims",
        "signals",
        "opportunities",
        "briefs",
        "projects",
        "research_requests",
        "tasks",
        "research_runs",
        "detected_changes",
    }
    assert expected.issubset(tables)
