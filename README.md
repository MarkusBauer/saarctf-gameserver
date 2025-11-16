saarCTF Gameserver Framework
============================

This repository contains the gameserver we used to organize our first attack-defense CTF - saarCTF 2020. 
If you want to build your own CTF with this framework: contact us for additional explanations.

This CTF infrastructure was build in a two-years-effort by @MarkusBauer, 
with additional contributions by [Jonas Bushart](https://github.com/jonasbb), Patrick Schmelzeisen, Niklas Beierl, and Simon Einzinger.


Structure
---------
- Central databases: PostgresSQL, Redis, RabbitMQ
- Central gameserver *(folder `controlserver`)*: Tick timer, dispatches checker scripts, calculate ranking and create scoreboard
- Checker script workers *(folder `checker_runner`)*: Run the checker scripts
- Submission Server: Accept flags from the participants
- VPN Server: Wireguard/OpenVPN servers for each team with additional monitoring / IPTables controller / tcpdump.


Setup
-----
- Setup a PostgreSQL database, a redis database and a RabbitMQ server (see below).
- `make deps`
- `npm install && npm run build`
- Write `config.yaml` (see [config.sample.yaml](config.sample.yaml))
- `alembic upgrade head`

Scoreboard and submission server need additional setup:
- cd scoreboard
- npm install && npm run build
- [Flag submission server build instructions](./flag-submission-server/README.md)


Run gameserver
--------------
`export FLASK_APP=controlserver/app.py` is required for most commands. So is either `run.sh` or `. venv/bin/activate`.

- Main server: `flask run --host=0.0.0.0`
- Celery worker: `celery -A checker_runner.celery_cmd worker -Ofair -E -Q celery,tests,broadcast --concurrency=16 --hostname=ident@%h`
- Celery control panel: `celery -A checker_runner.celery_cmd flower --port=5555`


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
Repeat if necessary.


Flags
-----
Current format: `SAAR\{[A-Za-z0-9-_]{32}\}`. 
Example: `SAAR{8VHsWgEACAD-_wAAfQScbWZat3KXyYe9}`

The prefix `SAAR` can be changed in `config.yaml`: set `flag_prefix` to something else (4 upper chars only so far).


Folders
-------
- `controlserver`: The main components (timer, scoreboard, scoring, dispatcher, ...)
- `checker_runner`: The celery worker code running the checker scripts
- `gamelib`


Configuration
-------------
To test, copy [`config.sample.yaml`](config.sample.yaml) to `config.yaml` and adjust if needed. 

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


ENOFLAG Service Interface
-------------------------
We support [enochecker services](https://github.com/enowars/specification) in alpha state.
How? Configure a service like this:
- `checker_timeout`: your tick time (at least 60 seconds with current code)
- `checker_runner`: `eno:EnoCheckerRunner` or a subclass
- `runner_config`: `{"url": "http://localhost:5008"}`
- `checker_subprocess`: false
- `checker_script_dir`: empty
- `checker_script`: empty

Set as usual:
- `flag_ids`: `['custom', 'custom', ...]`  for every putflag that uses attack_info
  > NO SPACES ALLOWED!
- `num_payloads`: number of flag variants
- `flags_per_tick`: number of flag variants

Checkout `config.sample.yaml`, section `runner`. 
Please have enough celery workers available, we suggest teams*services.


Developers
----------
For type checking do `make check`.

To prepare unit tests, copy `config.sample.yaml` to `config.test.yaml` and configure:
- an empty postgresql database (will be wiped during tests)
- an empty redis database
- a working rabbitmq connection

Then you can do `make tests`.

The docker setup is more or less proof-of-concept, we run things bare-metal.


More
----
There are many more things implemented here, for example VPN / network handling, which require additional setup.
Also, there are many utilities (in `/scripts`) which might help you with typical situations.
Most of the stuff has little documentation so far.
