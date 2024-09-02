saarCTF Gameserver Framework
============================

This repository contains the gameserver we used to organize our first attack-defense CTF - saarCTF 2020. 
If you want to build your own CTF with this framework: contact us for additional explanations.

This CTF infrastructure was build in a two-years-effort by @MarkusBauer, 
with additional contributions by [Jonas Bushart](https://github.com/jonasbb) and Patrick Schmelzeisen. 


Structure
---------
- Central databases: PostgresSQL, Redis, RabbitMQ
- Central gameserver *(folder `controlserver`)*: Round timer, dispatches checker scripts, calculate ranking and create scoreboard
- Checker script workers *(folder `checker_runner`)*: Run the checker scripts
- Submission Server: Accept flags from the participants
- VPN Server: OpenVPN-Servers for each team with additional monitoring / IPTables controller / tcpdump.


Setup
-----
- Setup a PostgreSQL database, a redis database and a RabbitMQ server (see below).
- `make deps`
- `npm install && npm run build`
- Write `config.json`
- `alembic upgrade head`


Run gameserver
--------------
`export FLASK_APP=controlserver/app.py` is required for most commands.

- Main server: `flask run --host=0.0.0.0`
- Celery control panel: `celery -A checker_runner.celery_cmd flower --port=5555`
- Celery worker: `celery -A checker_runner.celery_cmd worker -Ofair -E -Q celery,broadcast --concurrency=16 --hostname=ident@%h`


Setup RabbitMQ
--------------
```shell
# Warning: Binds to all interfaces by default!
apt install rabbitmq-server
rabbitmqctl add_vhost saarctf
rabbitmqctl add_user saarctf 123456789
rabbitmqctl set_permissions -p saarctf saarctf '.*' '.*' '.*'
rabbitmqctl set_user_tags saarctf administrator
rabbitmq-plugins enable rabbitmq_management
systemctl restart rabbitmq-server
```


Flags
-----
Current format: `SAAR\{[A-Za-z0-9-_]{32}\}`. 
Example: `SAAR{8VHsWgEACAD-_wAAfQScbWZat3KXyYe9}`


Folders
-------
- `controlserver`: The main components (timer, scoreboard, scoring, dispatcher, ...)
- `checker_runner`: The celery worker code running the checker scripts
- `gamelib`


Configuration
-------------
To test, copy `config.sample.json` to `config.json` and adjust if needed. 
JSON keys starting with `__` are stripped. 

To deploy, you can use environment variables:
- `SAARCTF_CONFIG` path to config.json file
- `SAARCTF_CONFIG_DIR` folder where config.json is located, and additional files will be stored (VPN config, VPN secrets etc). Default: root of this repository.
- Set `SAARCTF_NO_RLIMIT` if you have to run checkers without limit (e.g. Chromium)


Scoring
-------
The formulas to compute offensive/defensive/SLA scores are [on the webpage](https://ctf.saarland/rules), 
including a description of the details.
On the gameserver side, there are several factors you can use to adjust scores (all in `config.json` `"scoring":{...}`):
- `nop_team_id`: you cannot submit flags from this team
- `flags_rounds_valid` (default 10) more ticks means a bigger initial peak for new exploits, less ticks mean more time pressure
- `off_factor` scale offensive points up/down by this factor
- `def_factor` scale defensive points up/down by this factor
- `sla_factor` scale SLA points up/down by this factor
  Note that the defensive score formula contains a reference to SLA points, thus, the `sla_factor` also influences defensive scores.

Suggestions for saarCTF are default settings (1/10/1.0/1.0/1.0). 
Suggestions for our small workshop are (0/20/2.5/1.5/1.0). 
