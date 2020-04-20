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
- Create virtualenv with python 3.6+ and activate
- `python3 -m pip install -r requirements.txt`
- `npm install && npm run build`
- Write `config.json`
- `export FLASK_APP=controlserver/app.py`
- `flask db upgrade`


Run gameserver
--------------
`export FLASK_APP=controlserver/app.py` is required for most commands.

- Main server: `flask run --host=0.0.0.0`
- Celery control panel: `celery -A checker_runner flower --port=5555`
- Celery worker: `celery -A checker_runner worker -Ofair -E -Q celery,broadcast --concurrency=16 --hostname=ident@%h`


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

