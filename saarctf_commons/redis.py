import redis

from saarctf_commons.config import config


class NamedRedisConnection(redis.Connection):
    name: str = ''

    def on_connect(self) -> None:
        redis.Connection.on_connect(self)
        if self.name:
            self.send_command("CLIENT SETNAME", self.name.replace(' ', '_'))
            self.read_response()

    @classmethod
    def set_clientname(cls, name: str, overwrite: bool = False) -> None:
        """
        Set the name of all future redis connections.
        :param name:
        :param overwrite: Overwrite an already existing name?
        :return:
        """
        if overwrite or not cls.name:
            cls.name = name


redis_default_connection_pool: redis.ConnectionPool | None = None


def get_redis_connection() -> redis.StrictRedis:
    """
    :return: A new Redis connection (possibly from a connection pool). Name is already set.
    """
    global redis_default_connection_pool
    if not redis_default_connection_pool:
        redis_default_connection_pool = redis.ConnectionPool(connection_class=NamedRedisConnection, **config.REDIS)
    r = redis.StrictRedis(connection_pool=redis_default_connection_pool)
    return r
