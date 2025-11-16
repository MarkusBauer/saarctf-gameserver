import logging
import os


class DefaultAttributesFilter(logging.Filter):
    def __init__(self, attributes: dict) -> None:
        super().__init__()
        self._default_attrs = attributes

    def filter(self, record: logging.LogRecord) -> bool:
        for k, v in self._default_attrs.items():
            if not hasattr(record, k):
                setattr(record, k, v)
        return True


def setup_script_logging(component_name: str, logfile: str | None = None) -> None:
    format: str = "%(asctime)s [%(levelname)s]  %(message)s"
    logging.basicConfig(level=logging.INFO, format=format)
    logging.root.addFilter(DefaultAttributesFilter({"event.source": component_name}))

    if logfile is not None:
        fh = logging.FileHandler(logfile)
        fh.setLevel(logging.INFO)
        fh.setFormatter(logging.Formatter(format))
        logging.root.addHandler(fh)

    add_ecs_logging()


def add_ecs_logging() -> None:
    ecs_logfile = os.environ.get("ECS_LOGFILE", None)
    if ecs_logfile:
        import ecs_logging

        fh = logging.FileHandler(ecs_logfile)
        fh.setLevel(logging.INFO)
        fh.setFormatter(ecs_logging.StdlibFormatter())
        logging.root.addHandler(fh)
