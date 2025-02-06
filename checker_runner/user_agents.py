"""
Provide a list of user agents that the gameserver/gamelib can use
"""
import random
from pathlib import Path
import requests

_default_user_agent_file = Path.home() / 'user-agents.txt'


class UserAgentCollector:
    def __init__(self) -> None:
        self.agents: set[str] = set()

    def write(self, f: Path) -> None:
        f.write_text('\n'.join(sorted(self.agents)))
        print(f'wrote {len(self.agents)} user-agents')

    def collect_api(self) -> None:
        response = requests.get('https://github.com/microlinkhq/top-user-agents/raw/refs/heads/master/src/index.json')
        if response.status_code != 200:
            print(response)
            print(response.text)
            raise Exception('User agent "api" down')
        self.agents.update(response.json())

    def collect_requests(self) -> None:
        count_versions = max(10, int(len(self.agents) * 0.4))
        count_versions_rnd = max(5, int(len(self.agents) * 0.15))
        self.agents.add(f'python-requests/{requests.__version__}')

        releases = requests.get('https://pypi.org/pypi/requests/json').json()['releases']
        version_strings = [k for k, v in releases.items() if not any(artifact['yanked'] for artifact in v)]
        versions = [tuple(map(int, v.split('.'))) for v in version_strings]
        versions = [v for v in versions if v[0] >= 2]  # remove too old
        versions.sort(reverse=True)
        for v in versions[:count_versions]:
            self.agents.add(f'python-requests/{v[0]}.{v[1]}.{v[2]}')

        max_b = max(b for a, b, c in versions)
        max_c = max(c for a, b, c in versions)
        for _ in range(count_versions_rnd):
            b = random.randint(0, max_b + 1)
            c = random.randint(0, max_c + 1)
            self.agents.add(f'python-requests/2.{b}.{c}')


def init_celery_environment() -> None:
    if not _default_user_agent_file.exists():
        collector = UserAgentCollector()
        collector.collect_api()
        collector.collect_requests()
        collector.write(_default_user_agent_file)


if __name__ == '__main__':
    collector = UserAgentCollector()
    collector.collect_api()
    collector.collect_requests()
    collector.write(_default_user_agent_file)
