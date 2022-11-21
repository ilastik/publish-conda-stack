import re
from itertools import chain
from typing import List, Tuple, Union


def labels_to_upload_string(label_list: List[str]) -> str:
    """generates a string suitable for anaconda upload

    Examples:

    >>> labels_to_upload_string(['debug', 'devel'])
    '--label debug --label devel'
    >>> labels_to_upload_string([])
    ''
    """
    return " ".join(f"--label {label}" for label in label_list)


def labels_to_search_args(destination_channel: str, label_list: List[str]) -> List[str]:
    """generates a string suitable for conda search

    Examples:

    >>> labels_to_search_args('mychannel', ['debug', 'devel'])
    ['--channel', 'mychannel/label/debug', '--channel', 'mychannel/label/devel']

    >>> labels_to_search_args('mychannel', [])
    []
    """
    return list(
        chain(
            *[
                ("--channel", f"{destination_channel}/label/{label}")
                for label in label_list
            ]
        )
    )


def strip_label(channel_string: str) -> Tuple[str, Union[str, None]]:
    """Remove label from channel string

    Args:
        channel_string: string that includes label to a channel

    Returns:
        tuple: (string with channel only, label string or None)

    Examples:

    >>> strip_label("some-channel/label/some-label")
    ('some-channel', 'some-label')
    >>> strip_label("some-channel")
    ('some-channel', None)
    """
    regex = re.compile("/label/" + "(?P<label>[a-zA-Z0-9\-]+)" + "\Z")
    res = regex.search(channel_string)
    if res is None:
        return channel_string, None
    else:
        label = res.groupdict()["label"]
        return channel_string.split(f"/label/{label}")[0], label
