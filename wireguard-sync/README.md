# About

Asyncio python tool that synchronizes local wireguard interfaces with configuration 
provided by players in saarctf-webapge.

# WARNING

This thing fucks around with your network settings, don't run it on your local
machine if you don't know what you are doing. Depending on load it also might do a lot
of `fsync`.

# Setup

Poetry dependencies and Python3.12.
`poetry install`

# Usage

Configure via env vars or `.env` file in working dir.
For available / required vars, check `.env.example`.

`python wireguard_sync`

# Development

Docker compose setup connects to a local docker-compose instance of saarctf-webpage
and creates the interfaces in a docker container. 
