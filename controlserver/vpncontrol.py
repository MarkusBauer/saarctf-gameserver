import time
from enum import Enum
from typing import List, Tuple, Optional

from controlserver.logger import log
from controlserver.models import Team, LogMessage
from saarctf_commons.redis import get_redis_connection


class VpnStatus(Enum):
	OFF = 'off'
	ON = 'on'
	TEAMS_ONLY = 'team'


class VPNControl:
	def __init__(self) -> None:
		self.redis = get_redis_connection()

	def get_state(self) -> VpnStatus:
		b = self.redis.get('network:state')
		if b == b'on':
			return VpnStatus.ON
		if b == b'team':
			return VpnStatus.TEAMS_ONLY
		return VpnStatus.OFF

	def set_state(self, state: VpnStatus) -> None:
		old_state = self.get_state()
		onoff: str = state.value
		self.redis.set('network:state', onoff)
		self.redis.publish('network:state', onoff)
		if old_state != state:
			if state == VpnStatus.ON:
				log('vpn', 'Network open', level=LogMessage.IMPORTANT)
			elif state == VpnStatus.TEAMS_ONLY:
				log('vpn', 'Network open within teams only', level=LogMessage.IMPORTANT)
			else:
				log('vpn', 'Network closed', level=LogMessage.IMPORTANT)
			time.sleep(0.5)  # delay further CTF events (e.g. checker script dispatcher) until the firewall is really open

	def get_banned_teams(self) -> List[Tuple[Team, Optional[int]]]:
		"""
		:return: List of (banned team, tick where ban gets lifted)
		"""
		ids = map(int, self.redis.smembers('network:banned'))
		result = []
		for id in sorted(ids):
			tick = self.redis.get(f'network:bannedteam:{id}')
			tick = int(tick) if tick else None
			team = Team.query.filter(Team.id == id).first()
			if team:
				result.append((team, tick))
		return result

	def ban_team(self, team_id: int, until_tick: Optional[int]) -> None:
		if not team_id:
			return
		if until_tick == 0:
			until_tick = None
		self.redis.sadd('network:banned', team_id)
		self.redis.set(f'network:bannedteam:{team_id}', until_tick or '')
		self.redis.publish('network:ban', str(team_id))
		if until_tick:
			log('vpn', f'Banned team #{team_id} until tick {until_tick}')
		else:
			log('vpn', f'Banned team #{team_id}')

	def unban_team(self, team_id: int) -> None:
		self.redis.srem('network:banned', team_id)
		self.redis.delete(f'network:bannedteam:{team_id}')
		self.redis.publish('network:unban', str(team_id))
		log('vpn', f'Removed ban from team #{team_id}')

	def unban_for_tick(self, tick: int) -> None:
		ids = self.redis.smembers('network:banned')
		for id_bytes in ids:
			id = int(id_bytes.decode())
			until = self.redis.get(f'network:bannedteam:{id}')
			if until and int(until) == tick:
				self.unban_team(id)

	def get_open_teams(self) -> List[Team]:
		ids = map(int, self.redis.smembers('network:permissions'))
		result = []
		for id in sorted(ids):
			team = Team.query.filter(Team.id == id).first()
			if team:
				result.append(team)
		return result

	def add_permission_team(self, team_id: int) -> None:
		if not team_id:
			return
		self.redis.sadd('network:permissions', team_id)
		self.redis.publish('network:add_permission', str(team_id))
		log('vpn', f'Open network for team #{team_id}')

	def remove_permission_team(self, team_id: int) -> None:
		self.redis.srem('network:permissions', team_id)
		self.redis.publish('network:remove_permission', str(team_id))
		log('vpn', f'Close network for team #{team_id}')
