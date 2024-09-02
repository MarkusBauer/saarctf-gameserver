import os
import sys
from typing import Optional

from sqlalchemy import create_engine, Column, Integer, String, Boolean, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from saarctf_commons.redis import NamedRedisConnection
from saarctf_commons.config import config, load_default_config
from controlserver.models import Team, db_session, init_database
from scripts.sync_teams_http import import_logo

"""
NO ARGUMENTS
Sync teams with a provided SQLite database from the website
"""

webdb = create_engine(config.CONFIG['databases']['website'])
base = declarative_base()
session = sessionmaker()
session.configure(bind=webdb)


class WebsiteTeamProfile(base):
    __tablename__ = 'mainpage_teamprofile'
    user_id = Column(Integer, ForeignKey('auth_user.id'), primary_key=True)
    user = relationship("WebsiteTeam", back_populates="team_profile")
    is_team = Column(Boolean)
    team_id = Column(Integer)
    website = Column(String)
    logo = Column(String)

    def find_logo_image(self) -> Optional[str]:
        if self.logo:
            logo_path = config.CONFIG['logo_input_path']
            if os.path.exists(os.path.join(logo_path, self.logo)):
                return os.path.join(logo_path, self.logo)
        return None


class WebsiteTeam(base):
    __tablename__ = 'auth_user'
    id = Column(Integer, primary_key=True)
    username = Column(String, nullable=False)
    last_name = Column(String)  # "affiliation"
    is_active = Column(Boolean)
    team_profile = relationship(WebsiteTeamProfile, uselist=False, back_populates="user")


def add_team(wsteam: WebsiteTeam) -> None:
    if wsteam.team_profile.team_id is None:
        raise ValueError('Need team_id')
    team = Team(id=wsteam.team_profile.team_id, name=wsteam.username, affiliation=wsteam.last_name, website=wsteam.team_profile.website)
    db_session().add(team)
    db_session().commit()
    import_logo(team, wsteam.team_profile.find_logo_image())
    print(f'Added  team "{wsteam.username}".')


def update_team(team: Team, wsteam: WebsiteTeam) -> None:
    team.name = wsteam.username
    team.affiliation = wsteam.last_name
    team.website = wsteam.team_profile.website
    db_session().add(team)
    import_logo(team, wsteam.team_profile.find_logo_image())
    print(f'Update team "{team.name}".')


def main():
    init_database()
    should_delete = '--delete' in sys.argv
    s = session()
    if '--offline' in sys.argv:
        webteams = []
    else:
        webteams = s.query(WebsiteTeam).join(WebsiteTeamProfile) \
            .filter(WebsiteTeam.is_active == True, WebsiteTeamProfile.is_team == True, WebsiteTeamProfile.team_id.isnot(None)).all()
    teams = {team.id: team for team in Team.query.all()}
    if config.SCORING.nop_team_id and config.SCORING.nop_team_id not in teams:
        team = Team(id=config.SCORING.nop_team_id, name='NOP')
        db_session().add(team)
        teams[team.id] = team
    for webteam in webteams:
        if webteam.team_profile.team_id in teams:
            update_team(teams[webteam.team_profile.team_id], webteam)
            del teams[webteam.team_profile.team_id]
        else:
            add_team(webteam)
    # handle teams in this DB that are not present in the website
    for id, team in teams.items():
        if id == config.SCORING.nop_team_id:
            import_logo(team, None)
        elif should_delete:
            team.delete()
            print(f'Deleted team "{team.name}".')
        else:
            print(f'Team not found on website: #{team.id} "{team.name}". Use --delete to drop.')
            import_logo(team, None)
    db_session().commit()


if __name__ == '__main__':
    load_default_config()
    config.set_script()
    NamedRedisConnection.set_clientname('script-' + os.path.basename(__file__))
    main()
