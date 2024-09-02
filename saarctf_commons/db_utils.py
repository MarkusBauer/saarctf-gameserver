import logging
import time
from functools import wraps
from typing import Callable, TypeVar, ParamSpec
from sqlalchemy.exc import SQLAlchemyError

T = TypeVar('T')
P = ParamSpec('P')


def retry_on_sql_error(attempts: int = 3, sleeptime: float = 0.5) -> Callable[[Callable[P, T]], Callable[P, T]]:
    def decorator(func: Callable[P, T]) -> Callable[P, T]:
        @wraps(func)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            failures = 0
            while True:
                try:
                    result: T = func(*args, **kwargs)
                    if failures > 0:
                        logging.warning(f'Retry of {func.__name__} succeeded (attempt {failures + 1}/{attempts}).')
                    return result
                except (SQLAlchemyError, ConnectionResetError) as e:
                    failures += 1
                    if failures < attempts:
                        logging.warning(
                            f'Retrying {func.__name__} (attempt {failures + 1}/{attempts}) after SQL error {str(e)}'
                        )
                        time.sleep(sleeptime)
                    else:
                        raise e

        return wrapper

    return decorator
