from logging import config, root


def force_schema(url_or_hostname: str) -> str:
    """
    Force a "url" to have a schema, if none is present, guess https://.
    """
    if url_or_hostname.startswith("http://") or url_or_hostname.startswith("https://"):
        return url_or_hostname
    else:
        return f"https://{url_or_hostname}"


LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {
        "console": {
            "formatter": "default_formatter",
            "class": "logging.StreamHandler",
        },
    },
    "root": {
        "handlers": ["console"],
        "level": "INFO",
    },
    "loggers": {},
    "formatters": {
        "default_formatter": {
            "format": "%(asctime)s | %(levelname)s | %(message)s | %(name)s | " "%(filename)s:%(lineno)s",
        },
    },
}


def configure_logging() -> None:
    config.dictConfig(LOGGING)

    try:
        from saarctf_commons.logging_utils import add_ecs_logging, DefaultAttributesFilter
        root.addFilter(DefaultAttributesFilter({"event.source": 'wireguard-sync'}))
        add_ecs_logging()
    except ImportError:
        pass
