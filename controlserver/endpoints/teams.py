"""
Displays log messages - as list or single entry.
"""
import datetime
from typing import List

from flask import Blueprint, render_template, request, redirect, url_for
from flask_sqlalchemy import Pagination, BaseQuery
from sqlalchemy import or_, func, and_

from controlserver.models import Team, db, TeamTrafficStats
from saarctf_commons import config

app = Blueprint('teams', __name__)


def my_sum(x: List):
	if len(x) == 0: return None
	s = x[0]
	for y in x[1:]:
		s += y
	return s


@app.route('/teams/', methods=['GET'])
@app.route('/teams/<int:page>', methods=['GET'])
def teams_index(page=1):
	per_page = 1000
	order = request.args.get('sort', 'name')
	direction = request.args.get('dir', 'asc')
	query: BaseQuery = Team.query
	if '.' not in order:
		order_columns = [getattr(Team, order)]
		if order == 'vpn_connected':
			order_columns.append(Team.vpn2_connected)
		if direction == 'desc':
			order_columns = [col.desc() for col in order_columns]
		query = query.order_by(*order_columns)
	elif order.startswith('traffic.'):
		order = order[8:]
		if order.startswith('sum.'):
			pattern = order[4:]
			if '.' in pattern:
				suffix, prefix = pattern.split('.')
			else:
				suffix, prefix = pattern, ''
			cols = [column for name, column in TeamTrafficStats.__dict__.items() if name.endswith(suffix) and name.startswith(prefix)]
			assert len(cols) > 1
			order_column = my_sum(cols)
		else:
			order_column = getattr(TeamTrafficStats, order)
		if direction == 'desc':
			order_column = order_column.desc()
		query = query.order_by(order_column)
	else:
		raise Exception('Invalid order: ' + order)

	filter_online = request.args['filter_level'].split('|') if 'filter_level' in request.args else None
	if filter_online is not None:
		conditions = []
		if 'online' in filter_online: conditions.append((Team.vpn_connected == True) | (Team.vpn2_connected == True))
		if 'ever online' in filter_online: conditions.append(Team.vpn_last_connect != None)
		if 'offline' in filter_online: conditions.append((Team.vpn_connected == False) & (Team.vpn2_connected == False))
		query = query.filter(or_(*conditions))

	current_stats_timestamp = db.session.query(func.max(TeamTrafficStats.time)).scalar()
	if current_stats_timestamp is None:
		current_stats_timestamp = datetime.datetime.now()
	query = query.outerjoin(TeamTrafficStats, and_(Team.id == TeamTrafficStats.team_id, TeamTrafficStats.time == current_stats_timestamp))
	query = query.add_entity(TeamTrafficStats)
	print(str(query))

	teams: Pagination = query.paginate(page, per_page, error_out=False)
	if teams.pages < page:
		page = teams.pages if teams.pages > 0 else 1
		teams = query.paginate(page, per_page, error_out=False)

	return render_template(
		'teams.html', teams=teams,
		query_string=request.query_string.decode('utf8'),
		filter_online=filter_online,
		current_stats_timestamp=current_stats_timestamp,
		current_stats_timestamp_start=current_stats_timestamp - datetime.timedelta(seconds=60),
		Team=Team
	)


@app.route('/teams/view/<int:id>', methods=['GET'])
def teams_view(id=None):
	team = Team.query.filter(Team.id == id).first()
	if not team:
		return render_template('404.html'), 404
	traffic_stats: List[TeamTrafficStats] = \
		TeamTrafficStats.query.filter(TeamTrafficStats.team_id == id).order_by(TeamTrafficStats.time.desc()).limit(60).all()[::1]
	# "#97BBCD","#DCDCDC"
	graph1 = [{'label': "team's download", 'data': []}, {'label': "team's upload", 'data': []}]
	graph2 = [{'label': "team to team", 'data': []}, {'label': "total", 'data': []}]
	graph3 = [{'label': "team to team", 'data': []}, {'label': "total", 'data': []}]
	labels = []
	for ts in traffic_stats:
		labels.append(ts.time.timestamp())
		graph1[0]['data'].append(ts.down_teams_bytes + ts.down_game_bytes)
		graph1[1]['data'].append(ts.up_teams_bytes + ts.up_game_bytes)
		graph2[0]['data'].append(ts.down_teams_bytes + ts.up_teams_bytes)
		graph2[1]['data'].append(ts.down_game_bytes + ts.up_game_bytes)
		graph3[0]['data'].append(ts.down_teams_syns + ts.up_teams_syns)
		graph3[1]['data'].append(ts.down_game_syns + ts.up_game_syns)
	return render_template('teams_view.html', team=team, Team=Team, traffic_stats=traffic_stats,
						   graph1=graph1, graph2=graph2, graph3=graph3, labels=labels)


@app.route('/teams/byip/<ip>', methods=['GET'])
def teams_by_ip(ip=None):
	id = config.network_ip_to_id(ip)
	if not id:
		return render_template('404.html'), 404
	return redirect(url_for('teams.teams_view', id=id), code=302)
