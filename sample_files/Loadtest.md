Setup
-----
`mkdir /dev/shm/storage`
- Setup `demoservice.php` on localhost (symlink in webroot might be enough)
- Configure everything to use a seperate database / redis / rabbitmq
- `flask db upgrade` , import large_ctf.sql 
- Start gameserver, flower, celery worker, flag submitter

- Start the game
- Start exploiters using many instances of `python sample_files/demo_exploit.py repeat`

Useful commands
---------------
Exploiter:
`python demo_exploit.py repeat`

Cleanup of storage:
`find /dev/shm/storage -mmin +21 -type f -exec rm {} \;`

Automatic cleanup of storage:
`while true; do find /dev/shm/storage -mmin +21 -type f -exec rm {} \; ; sleep 120; done`

Check size of Postgresql database tables:
```sql
SELECT nspname || '.' || relname AS "relation", pg_size_pretty(pg_relation_size(C.oid)) AS "size", reltuples::bigint as "count"
  FROM pg_class C
  LEFT JOIN pg_namespace N ON (N.oid = C.relnamespace)
  WHERE nspname NOT IN ('pg_catalog', 'information_schema')
  ORDER BY pg_relation_size(C.oid) DESC
  LIMIT 20;
```

Total database size:
```sql
SELECT pg_size_pretty(sum(pg_relation_size(C.oid))) AS "total_size"
  FROM pg_class C LEFT JOIN pg_namespace N ON (N.oid = C.relnamespace)
  WHERE nspname NOT IN ('pg_catalog', 'information_schema');
```


Check Postgresql connections:
`SELECT sum(numbackends) FROM pg_stat_database;`
