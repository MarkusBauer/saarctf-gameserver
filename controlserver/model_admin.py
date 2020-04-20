from flask_admin import Admin
from flask_admin.contrib import sqla

from controlserver.models import db, Service, Team


class ServiceAdmin(sqla.ModelView):
	form_excluded_columns = ['package', 'setup_package']
	column_editable_list = ['name', 'checker_timeout', 'checker_enabled', 'num_payloads', 'flag_ids', 'flags_per_round']
	column_list = ['id', 'name', 'checker_script_dir', 'checker_script', 'checker_timeout', 'checker_enabled', 'checker_subprocess', 'num_payloads',
					'flag_ids', 'flags_per_round']
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


def register_admin(app):
	admin = Admin(app, name='saarCTF', template_mode='bootstrap3', base_template='admin_layout.html')
	admin.add_view(ServiceAdmin(Service, db.session))
	admin.add_view(TeamAdmin(Team, db.session))
