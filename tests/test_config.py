import pytest

from aeroeyes_monitoring_api.config import cors_allowed_origins_from_env


@pytest.mark.parametrize(
    ("configured_origins", "expected"),
    [
        ("", ()),
        (
            "http://localhost:5173",
            ("http://localhost:5173",),
        ),
        (
            "http://localhost:5173,http://127.0.0.1:5173",
            ("http://localhost:5173", "http://127.0.0.1:5173"),
        ),
        (
            " http://localhost:5173, ,http://127.0.0.1:5173, ",
            ("http://localhost:5173", "http://127.0.0.1:5173"),
        ),
        (
            "http://localhost:5173,http://localhost:5173,"
            "http://127.0.0.1:5173",
            ("http://localhost:5173", "http://127.0.0.1:5173"),
        ),
    ],
)
def test_cors_allowed_origins_from_env(
    monkeypatch,
    configured_origins: str,
    expected: tuple[str, ...],
) -> None:
    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", configured_origins)

    assert cors_allowed_origins_from_env() == expected


def test_cors_allowed_origins_from_missing_environment(monkeypatch) -> None:
    monkeypatch.delenv("CORS_ALLOWED_ORIGINS", raising=False)

    assert cors_allowed_origins_from_env() == ()
