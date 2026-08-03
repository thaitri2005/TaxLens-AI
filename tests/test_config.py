from taxlens.config import Settings


def test_database_url_uses_configured_values() -> None:
    settings = Settings(
        database_host="db.example.test",
        database_port=5433,
        database_name="legal",
        database_user="user",
        database_password="password",
    )

    assert settings.database_url == "postgresql+psycopg://user:password@db.example.test:5433/legal"
