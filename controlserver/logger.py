"""
Write messages to the central database log.
"""

import datetime
# import sys
import traceback
import time
from typing import Callable

from controlserver.models import LogMessage, db


def log(component: str, title: str, text: str = '', level: int = LogMessage.INFO, commit=True):
	"""
	Add a log message
	:param component: A component name (lowercase)
	:param title:
	:param text:
	:param level: One of LogMessage.XXX
	:param commit: commit the log message. If False, you have to call db.session.commit() yourself.
	:return:
	"""
	db.session.add(LogMessage(component=component, title=title, text=text, level=level, created=datetime.datetime.now()))
	if commit:
		db.session.commit()


def logException(component: str, e: Exception, errormessage: str = '{}: {}'):
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
	log(component, msg, stacktrace, level=LogMessage.ERROR)


def logResultOfExecution(component: str, function: Callable, args=(), success: str = None, successLevel: int = LogMessage.INFO, error: str = None,
						 reraise: bool = True):
	"""
	Execute function(*args) and check the result.
	In case it raises an exception, is is logged (using "error" message if given).
	If it finishes without exception, this is logged if "success" is given.
	:param component:
	:param function:
	:param args:
	:param success: (optional) Format string for successful execution. 1 parameter (execution time as float)
	:param successLevel: Log level of the "success" message
	:param error: (optional) Format string for exception log message (see #logException)
	:return:
	"""
	try:
		t = time.time()
		function(*args)
		if success:
			log(component, success.format(time.time() - t), level=successLevel)
	except Exception as e:
		if error:
			logException(component, e, error)
		if reraise:
			raise
