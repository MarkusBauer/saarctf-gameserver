"""
Displays log messages - as list or single entry.
"""

from flask import Blueprint, render_template, request
from flask_sqlalchemy import Pagination

from controlserver.models import LogMessage, db

app = Blueprint('log_messages', __name__)


@app.route('/log_messages/', methods=['GET'])
@app.route('/log_messages/<int:page>', methods=['GET'])
def log_messages_index(page=1):
	per_page = 50
	order = request.args.get('sort', 'created')
	direction = request.args.get('dir', 'desc')
	order_column = getattr(LogMessage, order)
	if direction == 'desc':
		order_column = order_column.desc()
	query = LogMessage.query.order_by(order_column)

	filter_level = request.args['filter_level'].split('|') if 'filter_level' in request.args else None
	if filter_level is not None:
		query = query.filter(LogMessage.level.in_([getattr(LogMessage, level) for level in filter_level]))

	filter_component = request.args.get('filter_component', '') or None
	if filter_component:
		query = query.filter(LogMessage.component == filter_component)

	filter_title = request.args.get('filter_title', '') or None
	if filter_title:
		query = query.filter(LogMessage.title.like(filter_title))

	log_messages: Pagination = query.paginate(page, per_page, error_out=False)
	if log_messages.pages < page:
		page = log_messages.pages if log_messages.pages > 0 else 1
		log_messages = query.paginate(page, per_page, error_out=False)

	components = [(c, c) for c, in db.session.query(LogMessage.component.distinct()).order_by(LogMessage.component).all()]
	return render_template(
		'log_messages.html', log_messages=log_messages,
		levels=LogMessage.LEVELS, query_string=request.query_string.decode('utf8'), components=components,
		filter_level=filter_level, filter_component=filter_component, filter_title=filter_title,
		LogMessage=LogMessage
	)


@app.route('/log_messages/view/<int:id>', methods=['GET'])
def log_messages_view(id=None):
	log_message = LogMessage.query.filter(LogMessage.id == id).first()
	if not log_message:
		return render_template('404.html'), 404
	return render_template('log_messages_view.html', log_message=log_message, LogMessage=LogMessage)
