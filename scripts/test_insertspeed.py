import time

from saarctf_commons.config import postgres_psycopg2
import psycopg2
import psycopg2.extras
import psycopg2.extensions

from sample_files.debug_sql_timing import timing

conn: psycopg2.extensions.connection = psycopg2.connect(postgres_psycopg2())
try:
	cursor: psycopg2.extensions.cursor = conn.cursor()

	timing()
	cursor.execute('DELETE FROM team_points WHERE round >= 500')
	conn.commit()
	timing('Delete')

	data = []
	for team in range(1, 502):
		for service in range(1, 11):
			data.append((team, service, 500, 1234, 567))

	timing('')
	cursor.executemany('INSERT INTO team_points (team_id, service_id, round, flag_points, sla_points) VALUES (%s, %s, %s, %s, %s)', data)
	conn.commit()
	timing('executemany')

	cursor.execute('DELETE FROM team_points WHERE round >= 500')
	conn.commit()

	timing('')
	psycopg2.extras.execute_values(cursor, 'INSERT INTO team_points (team_id, service_id, round, flag_points, sla_points) VALUES %s', data)
	conn.commit()
	timing('execute_values')

	cursor.execute('DELETE FROM team_points WHERE round >= 500')
	conn.commit()

	timing('')
	sql = 'INSERT INTO team_points (team_id, service_id, round, flag_points, sla_points) ' + \
		  'SELECT unnest(%(teams)s) , unnest(%(services)s), 500, unnest(%(flag_points)s), unnest(%(sla_points)s)'
	cursor.execute(sql, {
		'teams': [x[0] for x in data],
		'services': [x[1] for x in data],
		'flag_points': [x[3] for x in data],
		'sla_points': [x[4] for x in data]
	})
	conn.commit()
	timing('unnest')

	cursor.close()
finally:
	conn.close()

# ===== SAME WITH SQLALCHEMY =====

import controlserver.app
from controlserver.models import db, TeamPoints


def get_data():
	data = []
	for team in range(1, 502):
		for service in range(1, 11):
			data.append(TeamPoints(team_id=team, service_id=service, round=500, flag_points=1234, sla_points=567))
	return data


def get_data_map():
	data = []
	for team in range(1, 502):
		for service in range(1, 11):
			data.append(dict(team_id=team, service_id=service, round=500, flag_points=1234, sla_points=567))
	return data


TeamPoints.query.filter(TeamPoints.round >= 500).delete()
db.session.commit()

timing('')
data = get_data()
timing('SQLAlchemy prepared')
db.session.add_all(data)
db.session.commit()
timing('SQLAlchemy add_all')

TeamPoints.query.filter(TeamPoints.round >= 500).delete()
db.session.commit()

timing('')
data = get_data()
timing('SQLAlchemy prepared')
db.session.bulk_save_objects(data)
db.session.commit()
timing('SQLAlchemy bulk_save_objects')

TeamPoints.query.filter(TeamPoints.round >= 500).delete()
db.session.commit()

timing('')
data = get_data_map()
timing('SQLAlchemy prepared')
db.session.bulk_insert_mappings(TeamPoints, data)
db.session.commit()
timing('SQLAlchemy bulk_insert_mappings')
