import pytest

from publish_conda_stack.cmdutil import CondaCommand, conda_cmd_base


@pytest.fixture
def minimal_shared_config():
    return {
        "conda-source-channel-list": ["-c", "test-forge"],
        "upload-channel": "test-upload-forge",
    }


@pytest.mark.parametrize(
    "command",
    [
        CondaCommand.RENDER,
        CondaCommand.SEARCH,
        CondaCommand.BUILD,
    ],
)
def test_conda_default(command, minimal_shared_config):
    cmd_base = conda_cmd_base(command, minimal_shared_config)
    assert cmd_base[0] == "conda"


@pytest.mark.parametrize(
    "backend",
    [
        "conda",
        "mamba",
    ],
)
@pytest.mark.parametrize(
    "command",
    [
        CondaCommand.SEARCH,
        CondaCommand.BUILD,
    ],
)
def test_conda_backend_config(command, backend, minimal_shared_config):
    minimal_shared_config.update({"backend": backend})
    cmd_base = conda_cmd_base(command, minimal_shared_config)
    if command == CondaCommand.BUILD and backend == "mamba":
        # special case invocation of boa via conda mambabuild
        assert cmd_base[0:2] == ["conda", "mambabuild"]
    else:
        assert cmd_base[0] == backend


@pytest.mark.parametrize(
    "backend",
    [
        "conda",
        "mamba",
    ],
)
def test_conda_backend_render_always_conda(backend, minimal_shared_config):
    command = CondaCommand.RENDER
    cmd_base = conda_cmd_base(command, minimal_shared_config)

    assert cmd_base[0] == "conda"


@pytest.mark.parametrize(
    "labels",
    [
        ["blah"],
        ["forty", "two"],
    ],
)
def test_labels_added_to_search(labels, minimal_shared_config):
    minimal_shared_config.update({"labels": labels})
    cmd_base = conda_cmd_base(CondaCommand.SEARCH, minimal_shared_config)
    for label in labels:
        assert f"{minimal_shared_config['upload-channel']}/label/{label}" in cmd_base


@pytest.mark.parametrize(
    "command,expected",
    [
        (CondaCommand.RENDER, ["conda", "render", "--output", "-c", "test-forge"]),
        (
            CondaCommand.SEARCH,
            [
                "conda",
                "search",
                "--json",
                "--full-name",
                "--override-channels",
                "--channel",
                "test-upload-forge",
            ],
        ),
        (CondaCommand.BUILD, ["conda", "build", "-c", "test-forge"]),
    ],
)
def test_expected_command(command, expected, minimal_shared_config):
    cmd_base = conda_cmd_base(command, minimal_shared_config)
    assert cmd_base == expected


@pytest.mark.parametrize(
    "command",
    [
        CondaCommand.RENDER,
        CondaCommand.BUILD,
    ],
)
@pytest.mark.parametrize(
    "channel_list",
    [
        ["-c", "my42channel"],
        ["-c", "my42channel", "-c", "yetanotherone", "-c", "blah"],
    ],
)
def test_source_channel_list_updated(command, channel_list, minimal_shared_config):
    minimal_shared_config.update({"conda-source-channel-list": channel_list})
    cmd_base = conda_cmd_base(command, minimal_shared_config)
    assert " ".join(channel_list) in " ".join(cmd_base)
