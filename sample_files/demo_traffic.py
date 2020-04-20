import random
import time
from math import floor
from typing import List
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import controlserver.app
from controlserver.models import db, TeamPoints, Team, TeamTrafficStats


def random_subvec(old: List[int]):
	if not old:
		pc = random.randint(32, 5000)
		by = pc * random.randint(0x1000, 0xffff)
		syn = int(random.randint(5, 40) * pc / 100)
		synack = int(random.randint(30, 90) * syn / 100)
		return [pc, by, syn, synack]
	pc, by, syn, synack = old
	mod = random.uniform(0.8, 1.21)
	pc = int(round(pc * mod))
	if pc <= 10: pc = 10
	by = int(round(by * mod * random.uniform(0.9, 1.1)))
	if by <= 1000: by = 2000
	syn = int(round(random.randint(5, 40) * pc / 100))
	synack = int(round(random.randint(30, 90) * syn / 100))
	return [pc, by, syn, synack]


def random_vector(old: List[int]) -> List[int]:
	if not old:
		return random_subvec(old) + random_subvec(old) + random_subvec(old) + random_subvec(old)
	return random_subvec(old[:4]) + random_subvec(old[4:8]) + random_subvec(old[8:12]) + random_subvec(old[12:])


team_ids = [r[0] for r in db.session.query(Team.id).all()]
endtime = int(floor(time.time() // 60)) * 60

TeamTrafficStats.query.delete()
db.session.commit()

data = {}
for ts in range(endtime - 720 * 60, endtime + 1, 60):
	print(ts, '...', endtime)
	data = {team_id: random_vector(data.get(team_id, False)) for team_id in team_ids}
	TeamTrafficStats.efficient_insert(ts, data)
	db.session.commit()

print('[DONE]')
