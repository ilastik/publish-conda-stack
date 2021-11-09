from publish_conda_stack.core import get_rendered_version

import pytest


@pytest.mark.parametrize(
    "c_package_names,expected",
    [
        (
            "/some/path/abc-1.0.0-0py0,",
            (
                (
                    "abc",
                    "1.0.0",
                    "0py0",
                ),
            ),
        ),
        (
            "/some/path/abc-1.0.0-0py0\n/some/path/abc-1.0.0-1py2,",
            (
                (
                    "abc",
                    "1.0.0",
                    "0py0",
                ),
                (
                    "abc",
                    "1.0.0",
                    "1py2",
                ),
            ),
        ),
    ],
)
def test_get_rendered_version(mocker, c_package_names, expected):
    subprocess_mock = mocker.Mock()
    subprocess_mock.return_value = c_package_names.encode()
    mocker.patch("subprocess.check_output", new=subprocess_mock)
    res = get_rendered_version(
        "abc", "mock_path", "bld_env", {"source-channel-string": "ignore"}, None
    )

    assert len(res) == len(expected)


def test_get_rendered_version_raises(mocker):
    subprocess_mock = mocker.Mock()
    subprocess_mock.return_value = (
        "/some/path/abc-1.0.0-0py0\n/some/path/notabc-1.0.0-1py2,".encode()
    )
    mocker.patch("subprocess.check_output", new=subprocess_mock)
    with pytest.raises(RuntimeError):
        _ = get_rendered_version(
            "abc", "mock_path", "bld_env", {"source-channel-string": "ignore"}, None
        )
