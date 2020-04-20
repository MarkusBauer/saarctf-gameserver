"""
The one mighty main file. Initialized the Flask instance.
It is required to include this file everywhere you need flask or the database model.

You can execute this file to start the dev server.
"""

import os
import sys

from flask_admin import Admin

from saarctf_commons.config import EXTERNAL_TIMER

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from saarctf_commons import config

config.set_redis_clientname('controlserver')

from flask import Flask
from flask_apscheduler import APScheduler
from markupsafe import Markup

app = Flask(__name__)
app.config['SECRET_KEY'] = os.urandom(12).hex()
app.config['SQLALCHEMY_DATABASE_URI'] = config.postgres_sqlalchemy()
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['FLASK_ADMIN_FLUID_LAYOUT'] = True
# app.config['SQLALCHEMY_ECHO'] = True
app.config['JOBS'] = [
	{
		'id': 'job1',
		'func': 'controlserver.timer:notify',
		'args': (),
		'trigger': 'interval',
		'seconds': 1
	}
]

# init endpoints and models
import controlserver.endpoints.api
import controlserver.endpoints.pages
import controlserver.endpoints.checker_results
import controlserver.endpoints.log_messages
import controlserver.endpoints.teams
import controlserver.endpoints.flags
import controlserver.endpoints.services
from controlserver.models import init_models
from controlserver.model_admin import register_admin

app.register_blueprint(controlserver.endpoints.pages.app)
app.register_blueprint(controlserver.endpoints.checker_results.app)
app.register_blueprint(controlserver.endpoints.log_messages.app)
app.register_blueprint(controlserver.endpoints.teams.app)
app.register_blueprint(controlserver.endpoints.flags.app)
app.register_blueprint(controlserver.endpoints.services.app)
app.register_blueprint(controlserver.endpoints.api.app)
init_models(app)
register_admin(app)


# TODO hacky
@app.before_first_request
def init_timer():
	"""
	This function must be called once per game, and only once. You do not want multiple timers running in different processes.
	:return:
	"""
	from controlserver.timer import Timer
	if not EXTERNAL_TIMER and not Timer.initialized:
		from controlserver.events_impl import LogCTFEvents, DeferredCTFEvents, VPNCTFEvents
		Timer.listener.append(LogCTFEvents())
		Timer.listener.append(VPNCTFEvents())
		Timer.listener.append(DeferredCTFEvents())
		scheduler = APScheduler()
		scheduler.init_app(app)
		scheduler.start()
		Timer.initialized = True
		print('Master timer initialized')


@app.context_processor
def base_template_variables():
	from controlserver.timer import Timer
	return {
		'flower_url': config.FLOWER_URL,
		'coder_url': config.CODER_URL,
		'grafana_url': config.GRAFANA_URL,
		'scoreboard_url': config.SCOREBOARD_URL,
		'current_round': Timer.currentRound
	}


@app.template_filter('bool2html')
def filter_bool2html(b):
	return Markup('&#x2713;' if b else '&#x2717;')


@app.template_filter('thousand_spaces')
def filter_thousand_spaces(i):
	return '{:,}'.format(i).replace(',', ' ')


if __name__ == '__main__':
	import resource

	resource.setrlimit(resource.RLIMIT_AS, (4000 * 1024 * 1024, 4096 * 1024 * 1024))
	init_timer()
	app.run()
