import asyncio
import json
import os
from asyncio import Semaphore
from logging import getLogger
from pathlib import Path
from typing import Any, Awaitable, Callable, ParamSpec, TypeVar, cast
from urllib.parse import urljoin

from aiohttp import ClientSession
from aiohttp.client_exceptions import ClientConnectorError, ClientResponseError

from wireguard_sync import settings as global_settings
from wireguard_sync.exceptions import ApiError, ConfigurationError, InterfaceDoesNotExist
from wireguard_sync.network_lib import KeyPair, generate_key_pair, initialize_interface, sync
from wireguard_sync.rest_api import Interface, MinimalInterface
from wireguard_sync.utils import force_schema

AUTH_HEADER = "X-API-TOKEN"
LOGGER = getLogger(__name__)

P = ParamSpec("P")


class MergedSettings:
    """
    Read global settings with local overrides.
    """

    def __init__(self, local_settings: dict[str, Any] | None = None):
        self._local = local_settings or {}

    def __getattr__(self, name: str, *args, **kwargs) -> Any:
        if name in self._local:
            return self._local[name]
        return getattr(global_settings, name, *args, **kwargs)


class KeyStore:
    """
    Durably map public to private keys.
    """

    def __init__(self, settings: dict[str, Any] | None = None):
        self.settings = MergedSettings(settings)
        self._path = Path(self.settings.KEYSTORE_PATH)
        if self._path.is_file():
            with open(self._path, "r", encoding="utf-8") as f:
                self._keys = json.load(f)
        elif self._path.is_dir():
            raise ConfigurationError(f"Key store path: {self._path} is a directory")
        elif self._path.exists():
            raise ConfigurationError(f"Key store path: {self._path} is neither dir nor file?")
        else:
            self._keys = {}

    def __contains__(self, team_id: int | str):
        team_id = str(team_id)
        return team_id in self._keys

    def get_keys(self, team_id: int | str) -> KeyPair | None:
        """
        Get the public and private key for a team.

        :param team_id: The team ID to get the keys for.

        :return: The public and private key.
        """
        keys = self._keys.get(str(team_id))
        return KeyPair(*keys) if keys else None

    def put_keys(self, team_id: int, key_pair: KeyPair) -> None:
        """
        Put the public and private key for a team.

        :param team_id: The team ID to put the keys for.
        :param pub_key: The public key.
        :param priv_key: The private key.
        """
        self._keys[str(team_id)] = [*key_pair]
        tmp_file = self._path.with_suffix(".tmp")
        with open(tmp_file, "w", encoding="utf-8") as tmp:
            json.dump(self._keys, tmp)  # type: ignore
            tmp.flush()
            os.fsync(tmp.fileno())
        if self._path.exists():
            os.remove(self._path)
        # os.replace is atomic, as long as the files are on the same FS
        os.replace(tmp_file, self._path)


def reraise_api_errors(func):
    """
    Decorator to handle exceptions in API calls.
    """

    async def wrapper(*args, **kwargs):
        try:
            return await func(*args, **kwargs)
        except ClientResponseError as e:
            LOGGER.exception("AIOHTTP Response Error")
            # We should not receive any 4xx erros
            if str(e.status).startswith("4"):
                raise e
            raise ApiError from e
        except ClientConnectorError as e:
            LOGGER.exception("AIOHTTP Connection Error")
            raise ApiError from e

    return wrapper


class APIClient:
    def __init__(self, settings: dict[str, Any] | None = None) -> None:
        self.settings = MergedSettings(settings)
        self.semaphore = Semaphore(self.settings.API_CONCURRENCY)

        origin: str = self.settings.API_SERVER
        origin = force_schema(origin)
        base_path = self.settings.API_BASE
        base_path = base_path if base_path.endswith("/") else base_path + "/"
        self.base_url = urljoin(origin, base_path)

        self._settings = settings
        self._session: ClientSession | None = None

    def url(self, stub: str) -> str:
        return urljoin(self.base_url, stub)

    @property
    def session(self) -> ClientSession:
        """
        Get a session, creating a new one if needed.
        """
        if self._session is None or self._session.closed:
            self._session = ClientSession()
            self._session.headers.update({AUTH_HEADER: self.settings.API_TOKEN})
            return self._session
        return self._session

    @reraise_api_errors
    async def get_interfaces_to_update(self, all: bool = False) -> list[MinimalInterface]:
        async with self.semaphore:
            params = {}
            if not all:
                params["need_sync"] = ""
            result = await self.session.get(self.url("interfaces"), params=params, allow_redirects=False)
            result.raise_for_status()
            return await result.json()

    @reraise_api_errors
    async def get_interface(self, interface_id: int) -> Interface:
        async with self.semaphore:
            url = self.url(f"interface/{interface_id}")
            result = await self.session.get(url, allow_redirects=False)
            result.raise_for_status()
            return await result.json()

    @reraise_api_errors
    async def ack_interface(self, interface_id: int, last_modified: str | None) -> None:
        async with self.semaphore:
            url = self.url(f"interface/{interface_id}/sync")
            result = await self.session.post(url, data={"version": last_modified})
            result.raise_for_status()
            return await result.json()

    @reraise_api_errors
    async def set_pubk(self, interface_id: int, public_key: str) -> None:
        async with self.semaphore:
            url = self.url(f"interface/{interface_id}")
            result = await self.session.put(url, data={"public_key": public_key})
            result.raise_for_status()
            return await result.json()


ApiReturnType = TypeVar("ApiReturnType")


async def run_interface_up_hooks(ifname: str, team_id: int) -> None:
    """
    Run the interface up hooks for a newly initialized interface.
    """
    interface_up_hooks = global_settings.INTERFACE_UP_HOOKS
    for script in interface_up_hooks:
        hook = script.resolve()
        proc = await asyncio.create_subprocess_shell(
            str(hook),
            env={"dev": ifname, "team": str(team_id)},
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            LOGGER.error(f"Failed to run {hook=} {stdout.decode()=} {stderr.decode()=}")
        else:
            LOGGER.info(f"Ran {hook=} {stdout.decode()=} {stderr.decode()=}")


class InterfaceManager:
    def __init__(self, client: APIClient | None = None, keystore: KeyStore | None = None) -> None:
        LOGGER.info("Initializing InterfaceManager")
        self.client = client or APIClient()
        self.keystore = keystore or KeyStore()

    async def retry(self, func: Callable[P, Awaitable[ApiReturnType]], *args: P.args, **kwargs: P.kwargs) -> ApiReturnType:
        """
        Retry a function up to RETRY_LIMIT times with exponential backoff

        :param func: The function to call
        :param args: Positional arguments to pass to the function
        :param kwargs: Keyword arguments to pass to the function

        :return: The return value of the function
        """
        RETRY_LIMIT = 3
        error_count = 0
        while True:
            try:
                return await func(*args, **kwargs)
            except ApiError as e:
                if error_count >= RETRY_LIMIT:
                    raise e
                sleep_time = pow(2, error_count)
                LOGGER.exception(f"{func.__name__} failed, retrying in {sleep_time} seconds")
                error_count += 1
                await asyncio.sleep(sleep_time)

    async def initialize_all(self) -> None:
        LOGGER.info("Initializing all interfaces")
        need_init = await self.retry(self.client.get_interfaces_to_update, all=True)
        tasks = [self.fetch_and_sync(interface) for interface in need_init]
        await asyncio.gather(*tasks)

    async def fetch_and_sync(self, min_interface: MinimalInterface) -> None:
        interface = await self.retry(self.client.get_interface, min_interface["id"])
        team_id = interface["id"]

        key_pair = self.keystore.get_keys(team_id)
        api_pub_key = interface["public_key"]

        if key_pair and api_pub_key:
            assert key_pair.public_key == api_pub_key, f"Public key mismatch {team_id=} {api_pub_key=} {key_pair.public_key=}"

        if not key_pair and api_pub_key:
            raise ValueError(f"Missing private key for {team_id=} {api_pub_key=}")

        if not key_pair and not api_pub_key:
            LOGGER.info(f"Creating keypair for {team_id=}")
            key_pair = generate_key_pair()
            self.keystore.put_keys(team_id=team_id, key_pair=key_pair)
            # Key is saved to disk now ...

        key_pair = cast(KeyPair, key_pair)

        if not api_pub_key:
            await self.retry(self.client.set_pubk, interface["id"], public_key=key_pair.public_key)
            interface["public_key"] = key_pair.public_key

        try:
            sync(interface)
        except InterfaceDoesNotExist:
            LOGGER.warning(f"Interface {interface['id']} does not exist on the system")

            ifname = initialize_interface(interface, key_pair.private_key)
            await run_interface_up_hooks(ifname=ifname, team_id=interface["id"])
            sync(interface)

        LOGGER.info(f"Interface {interface['id']} synced")
        await self.retry(self.client.ack_interface, interface["id"], last_modified=interface["last_modified"])

    async def loop(self) -> None:
        while True:
            try:
                need_init = await self.client.get_interfaces_to_update(all=False)
                tasks = [self.fetch_and_sync(interface) for interface in need_init]
                await asyncio.gather(*tasks)
            except ApiError as e:
                LOGGER.error(f"API Error: {e}")

            # TODO: Only sleep if we finished too quickly
            LOGGER.info("Finished loop, sleeping")
            await asyncio.sleep(1)
