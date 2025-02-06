import asyncio
import sys
from pathlib import Path

# fix import paths for saarctf config
sys.path.append(str(Path(__file__).absolute().parent.parent.parent))
# fix import paths for "wireguard_sync" module
sys.path.append(str(Path(__file__).absolute().parent.parent))


from argparse import ArgumentParser, Namespace

from wireguard_sync import InterfaceManager, KeyStore
from wireguard_sync.network_lib import generate_key_pair
from wireguard_sync.utils import configure_logging


def generate_key_pairs(amount: int, key_store: KeyStore) -> None:
    for i in range(1, amount + 1):
        if i in key_store:
            print(f"Skipping team{i}")
            continue
        key_pair = generate_key_pair()
        key_store.put_keys(team_id=i, key_pair=key_pair)


async def main(args: Namespace) -> None:
    # TODO: Customize settings from cli args
    manager = InterfaceManager()
    if args.command == "generate":
        generate_key_pairs(amount=args.amount, key_store=manager.keystore)
    else:
        await manager.initialize_all()
        await manager.loop()


if __name__ == "__main__":
    parser = ArgumentParser()

    subparsers = parser.add_subparsers(dest="command", required=False)

    generate_parser = subparsers.add_parser("generate", help="Pregenreate key pairs")
    generate_parser.add_argument(
        "-a", "--amount", type=int, default=400, help="Amount of pregenerated key pairs (default: 400)"
    )

    args = parser.parse_args()
    configure_logging()

    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(main(args))
    finally:
        loop.run_until_complete(loop.shutdown_asyncgens())
        loop.close()
