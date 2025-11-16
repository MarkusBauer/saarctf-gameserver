import os
import sys
from argparse import ArgumentParser, Namespace
from typing import Dict, Optional

import requests

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from controlserver.models import Team, TeamLogo, db_session, init_database
from saarctf_commons.config import config, load_default_config
from saarctf_commons.redis import NamedRedisConnection

REQUEST_TIMEOUT = 5


def import_logo(team: Team, logo: Optional[str]) -> None:
    for path in (config.SCOREBOARD_PATH, config.SCOREBOARD_PATH_INTERNAL):
        if path is not None:
            (path / "logos").mkdir(parents=True, exist_ok=True)
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    logo_in = logo or os.path.join(
        root, "controlserver", "static", "img", "profile_dummy.png"
    )
    imghash = TeamLogo.store_logo_file(logo_in)
    team.logo = imghash


def import_logo_from_bytes(team: Team, data: bytes) -> None:
    for path in (config.SCOREBOARD_PATH, config.SCOREBOARD_PATH_INTERNAL):
        if path is not None:
            (path / "logos").mkdir(parents=True, exist_ok=True)
    imghash = TeamLogo.store_logo_bytes(data)
    team.logo = imghash


def import_logo_from_url(team: Team, fname: str) -> None:
    if not fname:
        import_logo(team, None)
        return
    # check if image is already present
    if team.logo is not None and team.logo in fname:
        return
    # download image
    if "website_logo_url" in config.CONFIG:
        url: str = config.CONFIG["website_logo_url"] + "/" + fname
    else:
        url = config.CONFIG["website_team_url"].split("?")[0]
        url = url.rstrip("/").rsplit("/", 2)[0]
        url += "/media/" + fname
    resp = requests.get(url, timeout=REQUEST_TIMEOUT)
    if resp.status_code == 200:
        import_logo_from_bytes(team, resp.content)
    else:
        print(f"Could not fetch logo {resp.status_code=}")


def add_team(remote_team: Dict) -> None:
    session = db_session()
    team = Team(
        id=remote_team["id"],
        name=remote_team["name"],
        affiliation=remote_team["affiliation"],
        website=remote_team["website"],
    )
    session.add(team)
    session.commit()
    import_logo_from_url(team, remote_team["logo"])
    session.add(team)
    print(f'Added  team "{team.name}".')


def update_team(team: Team, remote_team: Dict) -> None:
    team.name = remote_team["name"]
    team.affiliation = remote_team["affiliation"]
    team.website = remote_team["website"]
    import_logo_from_url(team, remote_team["logo"])
    db_session().add(team)
    print(f'Update team "{team.name}".')


def main(args: Namespace) -> None:
    init_database()
    should_delete = args.delete
    teams = {team.id: team for team in Team.query.all()}
    remote_teams = requests.get(
        config.CONFIG["website_team_url"], timeout=REQUEST_TIMEOUT
    ).json()["teams"]

    # Create Nop team if not existing
    if config.SCORING.nop_team_id and config.SCORING.nop_team_id not in teams:
        team = Team(id=config.SCORING.nop_team_id, name="NOP")
        db_session().add(team)
        teams[team.id] = team

    for remote_team in remote_teams:
        if remote_team["id"] in teams:
            update_team(teams[remote_team["id"]], remote_team)
            del teams[remote_team["id"]]
        else:
            add_team(remote_team)

    # handle teams in this DB that are not present in the remote
    for team_id, team in teams.items():
        if team_id == config.SCORING.nop_team_id:
            import_logo(team, None)
        elif should_delete:
            db_session().delete(team)
            print(f'Deleted team "{team.name}".')
        else:
            print(
                f'Team not found on website: #{team.id} "{team.name}". Use --delete to drop.'
            )
            import_logo(team, None)
    db_session().commit()


if __name__ == "__main__":
    load_default_config()
    config.set_script()
    NamedRedisConnection.set_clientname("script-" + os.path.basename(__file__))
    parser = ArgumentParser()
    parser.add_argument(
        "-d",
        "--delete",
        action="store_true",
        help="Delte teams from the server that are not on the remote",
    )

    main(parser.parse_args())
