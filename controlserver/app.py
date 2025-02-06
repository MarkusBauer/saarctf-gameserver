"""
The one mighty main file. Initialized the Flask instance.
It is required to include this file everywhere you need flask or the database model.

You can execute this file to start the dev server.
"""

import os
import sys
import threading

from controlserver.timer import init_cp_timer, run_master_timer
from saarctf_commons.metric_utils import setup_default_metrics

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from checker_runner.runner import celery_worker
from saarctf_commons.redis import NamedRedisConnection
from saarctf_commons.config import config, load_default_config

from flask import Flask
from flask_admin import Admin
from markupsafe import Markup


def _register_endpoints(app: Flask) -> None:
    import controlserver.endpoints.api
    import controlserver.endpoints.pages
    import controlserver.endpoints.checker_results
    import controlserver.endpoints.log_messages
    import controlserver.endpoints.teams
    import controlserver.endpoints.flags
    import controlserver.endpoints.metrics
    import controlserver.endpoints.services
    import controlserver.endpoints.patches
    app.register_blueprint(controlserver.endpoints.pages.app)
    app.register_blueprint(controlserver.endpoints.checker_results.app)
    app.register_blueprint(controlserver.endpoints.log_messages.app)
    app.register_blueprint(controlserver.endpoints.teams.app)
    app.register_blueprint(controlserver.endpoints.flags.app)
    app.register_blueprint(controlserver.endpoints.metrics.app)
    app.register_blueprint(controlserver.endpoints.services.app)
    app.register_blueprint(controlserver.endpoints.patches.app)
    app.register_blueprint(controlserver.endpoints.api.app)


def _register_processors(app: Flask) -> None:
    @app.context_processor
    def base_template_variables() -> dict:
        from controlserver.timer import Timer
        return {
            'flower_url': config.FLOWER_URL,
            'coder_url': config.CODER_URL,
            'grafana_url': config.GRAFANA_URL,
            'scoreboard_url': config.SCOREBOARD_URL,
            'current_round': Timer.current_tick,
            'current_tick': Timer.current_tick,
        }

    @app.template_filter('bool2html')
    def filter_bool2html(b: bool) -> Markup:
        return Markup('&#x2713;' if b else '&#x2717;')

    @app.template_filter('thousand_spaces')
    def filter_thousand_spaces(i: int) -> str:
        return '{:,}'.format(i).replace(',', ' ')


def start_timer_if_necessary() -> None:
    """
    This function must be called once per game, and only once. You do not want multiple timers running in different processes.
    :return:
    """
    from controlserver.timer import Timer
    if not config.EXTERNAL_TIMER and not Timer.initialized:
        thread = threading.Thread(target=run_master_timer, daemon=True, name='Timer Thread')
        thread.start()
        print('Master timer initialized')


def create_app() -> Flask:
    load_default_config()
    init_cp_timer()
    NamedRedisConnection.set_clientname('controlserver')
    celery_worker.init()
    start_timer_if_necessary()
    setup_default_metrics()

    app = Flask(__name__)
    app.config['SECRET_KEY'] = os.urandom(12).hex()
    app.config['FLASK_ADMIN_FLUID_LAYOUT'] = True

    _register_endpoints(app)

    _register_processors(app)

    # init models
    from controlserver.models import init_database
    from controlserver.model_admin import register_admin
    with app.app_context():
        init_database(app)
        register_admin(app)

    return app


if __name__ == '__main__':
    import resource

    resource.setrlimit(resource.RLIMIT_AS, (4000 * 1024 * 1024, 4096 * 1024 * 1024))
    app = create_app()
    app.run()
