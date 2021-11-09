from publish_conda_stack.core import get_rendered_version, CCPkgName

import pytest


@pytest.mark.parametrize(
    "c_package_names,expected",
    [
        (
            "/some/path/abc-1.0.0-0py0.tar.bz2",
            (
                CCPkgName(
                    "abc",
                    "1.0.0",
                    "0py0",
                ),
            ),
        ),
        (
            "/some/path/abc-1.0.0-0py0.tar.bz2\n/some/path/abc-1.0.0-1py2.tar.bz2",
            (
                CCPkgName(
                    "abc",
                    "1.0.0",
                    "0py0",
                ),
                CCPkgName(
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
    assert res == expected


def test_get_rendered_version_raises(mocker):
    subprocess_mock = mocker.Mock()
    subprocess_mock.return_value = "/some/path/abc-1.0.0-0py0.tar.bz2\n/some/path/notabc-1.0.0-1py2.tar.bz2".encode()
    mocker.patch("subprocess.check_output", new=subprocess_mock)
    with pytest.raises(RuntimeError):
        _ = get_rendered_version(
            "abc", "mock_path", "bld_env", {"source-channel-string": "ignore"}, None
        )


def test_get_rendered_version_ignores_patch_outputs(mocker):
    subprocess_mock = mocker.Mock()
    subprocess_mock.return_value = "Patch level ambiguous, selecting least deep\nPatch analysis gives:\n[[ RA-MD1--VE ]] - [[                                       0001-fix-whatever.patch ]]\n\nKey:\n\nR :: Reversible                       A :: Applicable\nY :: Build-prefix patch in use        M :: Minimal, non-amalgamated\nD :: Dry-runnable                     N :: Patch level (1 is preferred)\nL :: Patch level not-ambiguous        O :: Patch applies without offsets\nV :: Patch applies without fuzz       E :: Patch applies without emitting to stderr\n\n/some/path/abc-1.0.0-0py0whatever.tar.bz2\n".encode()
    mocker.patch("subprocess.check_output", new=subprocess_mock)
    expected = CCPkgName("abc", "1.0.0", "0py0whatever")

    res = get_rendered_version(
        "abc", "mock_path", "bld_env", {"source-channel-string": "ignore"}, None
    )

    assert len(res) == 1
    assert res[0] == expected
