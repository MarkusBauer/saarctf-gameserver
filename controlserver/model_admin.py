from flask import Flask
from flask_admin import Admin
from flask_admin.contrib import sqla

from controlserver.models import Service, Team, db_session


class ServiceAdmin(sqla.ModelView):
    form_excluded_columns = ['package', 'setup_package']
    column_editable_list = ['name', 'checker_timeout', 'checker_enabled', 'checker_runner', 'checker_route', 'num_payloads',
                            'flag_ids', 'flags_per_tick', 'ports']
    column_list = ['id', 'name', 'checker_runner',
                   'checker_script_dir', 'checker_script', 'checker_timeout', 'checker_enabled', 'checker_subprocess', 'checker_route',
                   'runner_config', 'num_payloads', 'flag_ids', 'flags_per_tick', 'ports']
    create_modal = True
    edit_modal = True
    column_display_pk = True
    pass


class TeamAdmin(sqla.ModelView):
    form_excluded_columns = ['logo', 'points']
    column_editable_list = ['name', 'affiliation', 'website']
    create_modal = True
    edit_modal = True
    column_display_pk = True
    pass


def register_admin(app: Flask) -> None:
    admin = Admin(app, name='saarCTF', template_mode='bootstrap3', base_template='admin_layout.html')
    admin.add_view(ServiceAdmin(Service, db_session()))
    admin.add_view(TeamAdmin(Team, db_session()))
