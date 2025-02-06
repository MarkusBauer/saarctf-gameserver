
Building
--------
You need `libev`, `openssl`, `libhiredis` and `libpq`. On Ubuntu: `apt install libev-dev libssl-dev libpq-dev postgresql-server-dev-all libhiredis-dev cmake`

Build using CMake: 
```
mkdir build
cd build
cmake -DCMAKE_BUILD_TYPE=Release ..
make
```


Usage
-----
```
./flag-submission-server <port> <threads>
```
Default port: 31337, default threads: 1.


Flag format
-----------
`SAAR{32-websafe-base64-bytes}` (example: `SAAR{vQA2AAYAAACXlPecBGL77CAqZOuU4BTa}`, regex `SAAR\{[A-Za-z0-9-_]{32}\}`)

Binary data consists of (all numbers are little-endian): 

- 2 bytes tick (this flag was stored)
- 2 bytes team id
- 2 bytes service id
- 2 payload bytes
- 16 bytes SHA256-HMAC (over the other parts of the flag)

Configure in [`flagchecker.h`](src/flagchecker.h) and [`flagchecker.cpp`](src/flagchecker.cpp). 


Configuration
-------------
In [`config.yaml`](../config.sample.yaml): set everything you need (database, redis, secret key, ...). This should be enough for most purposes.

In [`flagcache.cpp`](src/flagcache.cpp): Set flag rate and number of valid flags per service/team/round. 

In [`flagchecker.h`](src/flagchecker.h): Enable/disable what to check for. 

In [`database.cpp`](src/database.cpp): Enable or disable asynchronous commits.

Run `make` afterwards.


Database
--------
This server needs the database layout from the `saarctf` gameserver. It does not initialize the database itself.
