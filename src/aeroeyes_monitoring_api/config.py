import os


def cors_allowed_origins_from_env() -> tuple[str, ...]:
    configured_origins = os.environ.get("CORS_ALLOWED_ORIGINS", "")
    origins = (item.strip() for item in configured_origins.split(","))
    return tuple(dict.fromkeys(origin for origin in origins if origin))
