"""
Write messages to the central database log.
"""

import datetime
import logging
import time
# import sys
import traceback
from typing import Callable, Any, ParamSpec
from sqlalchemy.orm import Session

from controlserver.models import LogMessage, db_session_2
from saarctf_commons.db_utils import retry_on_sql_error

P = ParamSpec("P")

py_logger = logging.getLogger("log_messages")


def log(component: str, title: str, text: str = '', level: int = LogMessage.INFO) -> None:
    msg = title + ('' if not text else '\n' + text)
    py_logger.log(LogMessage.level_to_python(level), msg)
    _log(component, title, text, level)


@retry_on_sql_error(attempts=2)
def _log(component: str, title: str, text: str = '', level: int = LogMessage.INFO) -> None:
    """
    Add a log message
    :param component: A component name (lowercase)
    :param title:
    :param text:
    :param level: One of LogMessage.XXX
    :return:
    """
    with db_session_2() as session:
        log_to_session(session, component, title, text, level)
        session.commit()


def log_to_session(session: Session, component: str, title: str, text: str = '', level: int = LogMessage.INFO) -> None:
    """
    Add a log message
    :session: A SQL session to add log messages to
    :param component: A component name (lowercase)
    :param title:
    :param text:
    :param level: One of LogMessage.XXX
    :return:
    """
    session.add(LogMessage(component=component, title=title, text=text, level=level, created=datetime.datetime.now()))


def log_exception(component: str, e: Exception, errormessage: str = '{}: {}') -> None:
    """
    Log an error.
    :param component:
    :param e:
    :param errormessage: Format string with 2 parameters: exception class name and exception message (if given)
    :return:
    """
    msg = errormessage.format(e.__class__.__name__, e.args[0] if len(e.args) >= 1 else '')
    stacktrace = ''.join(traceback.format_exception(type(e), e, e.__traceback__))
    # print(stacktrace, file=sys.stderr)
    py_logger.exception(msg, exc_info=e)
    _log(component, msg, stacktrace, level=LogMessage.ERROR)


def log_result_of_execution(component: str, function: Callable[P, Any], args: P.args = (),
                            success: str | None = None, successLevel: int = LogMessage.INFO,
                            error: str | None = None, reraise: bool = True) -> None:
    """
    Execute function(*args) and check the result.
    In case it raises an exception, is is logged (using "error" message if given).
    If it finishes without exception, this is logged if "success" is given.
    :param component:
    :param function:
    :param args:
    :param success: (optional) Format string for successful execution. 1 parameter (execution time as float)
    :param successLevel: Log level of the "success" message
    :param error: (optional) Format string for exception log message (see #log_exception)
    :param reraise: (optional) Raise exceptions after logging
    :return:
    """
    try:
        t = time.time()
        function(*args)  # type: ignore
        if success:
            log(component, success.format(time.time() - t), level=successLevel)
    except Exception as e:
        if error:
            log_exception(component, e, error)
        if reraise:
            raise
