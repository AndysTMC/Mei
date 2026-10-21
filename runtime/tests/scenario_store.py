"""For process-level scenarios: let this test script give Mei requests, by writing the setting into
the store before the runtime starts (its D-Bus API only lets the Shell turn it on)."""

import os
from pathlib import Path

import msgspec

from mei.protocol import Clients
from mei.store import repo
from mei.store.db import Store


def allow_external_input() -> None:
    store = Store(Path(os.environ["MEI_DATA_DIR"]))
    revision, config = repo.get_config(store)
    with store.tx() as tx:
        repo.put_config(tx, revision, msgspec.structs.replace(config, clients=Clients(external_input=True)))
    store.close()
