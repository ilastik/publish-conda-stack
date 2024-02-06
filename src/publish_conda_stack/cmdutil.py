from enum import IntEnum, auto
from typing import List

from .util import labels_to_search_args

DEFAULT_BACKEND = "conda"


class CondaCommand(IntEnum):
    RENDER: int = auto()
    SEARCH: int = auto()
    BUILD: int = auto()


def conda_cmd_base(command: CondaCommand, shared_config: dict) -> List[str]:
    variant_config = shared_config.get("master-conda-build-config", None)
    variant_args = ["-m", variant_config] if variant_config else []

    # render is not supported in mamba, here we must use conda
    if command == CondaCommand.RENDER:
        args = ["conda"]
        args.extend(["render", "--output"])
        args.extend(shared_config["conda-source-channel-list"])
        args.extend(variant_args)
        return args

    backend = shared_config.get("backend", DEFAULT_BACKEND)
    if backend not in ["conda", "mamba"]:
        raise ValueError(
            f"Unknown backend: {backend}. Only `conda` and `mamba` are supported."
        )

    args = [backend]

    if command == CondaCommand.SEARCH:
        labels = shared_config.get("labels", [])
        args.extend(
            [
                "search",
                "--json",
                "--full-name",
                "--override-channels",
                "--channel",
                shared_config["upload-channel"],
            ]
        )
        args.extend(labels_to_search_args(shared_config["upload-channel"], labels))
        return args

    if command == CondaCommand.BUILD:
        if backend == "mamba":
            args = ["conda", "mambabuild"]
        else:
            args.extend(["build"])
        args.extend(shared_config["conda-source-channel-list"])
        args.extend(variant_args)
        return args

    raise ValueError(f"unknown command supplied. Got {command}")
