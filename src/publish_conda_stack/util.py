import re


def strip_label(channel_string: str) -> str:
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
    regex = re.compile(
        """
        /label/
        (?P<label>[a-zA-Z0-1\-]+)
        \Z
    """,
        re.X,
    )
    res = regex.search(channel_string)
    if res is None:
        return channel_string, None
    else:
        label = res.groupdict()["label"]
        return channel_string.split(f"/label/{label}")[0], label
