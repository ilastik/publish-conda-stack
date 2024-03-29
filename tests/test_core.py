import subprocess
from textwrap import dedent

import pytest

from publish_conda_stack.core import (
    CCPkgName,
    check_already_exists,
    get_rendered_version,
)


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
        # windows style line endings
        (
            "/some/path/abc-1.0.0-0py0.tar.bz2\r\n/some/path/abc-1.0.0-1py2.tar.bz2",
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
        "abc", "mock_path", "bld_env", {"conda-source-channel-list": ["-c", "ignore"]}
    )

    assert len(res) == len(expected)
    assert res == expected


def test_get_rendered_version_hyphen_pkg(mocker):
    """ensure package names with hyphens don't cause issues"""
    subprocess_mock = mocker.Mock()
    subprocess_mock.return_value = "/some/path/a-b-c-1.0.0-0py0.tar.bz2".encode()
    mocker.patch("subprocess.check_output", new=subprocess_mock)
    res = get_rendered_version(
        "a-b-c", "mock_path", "bld_env", {"conda-source-channel-list": ["-c", "ignore"]}
    )
    assert len(res) == 1
    assert res[0].package_name == "a-b-c"


def test_get_rendered_version_raises(mocker):
    subprocess_mock = mocker.Mock()
    subprocess_mock.return_value = "/some/path/abc-1.0.0-0py0.tar.bz2\n/some/path/notabc-1.0.0-1py2.tar.bz2".encode()
    mocker.patch("subprocess.check_output", new=subprocess_mock)
    with pytest.raises(RuntimeError):
        _ = get_rendered_version(
            "abc",
            "mock_path",
            "bld_env",
            {"conda-source-channel-list": ["-c", "ignore"]},
        )


def test_get_rendered_version_ignores_patch_outputs(mocker):
    subprocess_mock = mocker.Mock()
    subprocess_mock.return_value = "Patch level ambiguous, selecting least deep\nPatch analysis gives:\n[[ RA-MD1--VE ]] - [[                                       0001-fix-whatever.patch ]]\n\nKey:\n\nR :: Reversible                       A :: Applicable\nY :: Build-prefix patch in use        M :: Minimal, non-amalgamated\nD :: Dry-runnable                     N :: Patch level (1 is preferred)\nL :: Patch level not-ambiguous        O :: Patch applies without offsets\nV :: Patch applies without fuzz       E :: Patch applies without emitting to stderr\n\n/some/path/abc-1.0.0-0py0whatever.tar.bz2\n".encode()
    mocker.patch("subprocess.check_output", new=subprocess_mock)
    expected = CCPkgName("abc", "1.0.0", "0py0whatever")

    res = get_rendered_version(
        "abc", "mock_path", "bld_env", {"conda-source-channel-list": ["-c", "ignore"]}
    )

    assert len(res) == 1
    assert res[0] == expected


def test_check_already_exists(mocker):
    c_pkg_names = (CCPkgName("mypack", "1.0", "py38_0_hblah"),)
    shared_config = {
        "destination-channel": "mock-channel",
        "labels": ["test"],
        "upload-channel": "blah-forge",
    }

    subprocess_mock = mocker.Mock()
    subprocess_mock.return_value = dedent(
        """
    {
      "mypack": [
        {
          "build": "py38_0_hblah",
          "build_number": 0,
          "name": "mypack",
          "version": "1.0"
        }
      ]
    }
    """
    ).encode()
    mocker.patch("subprocess.check_output", new=subprocess_mock)

    pkgs_found = check_already_exists(c_pkg_names, shared_config)

    subprocess_mock.assert_called_once_with(
        [
            "conda",
            "search",
            "--json",
            "--full-name",
            "--override-channels",
            "--channel",
            "blah-forge",
            "--channel",
            "blah-forge/label/test",
            "mypack",
        ]
    )

    assert len(pkgs_found) == 1
    assert pkgs_found[0][0] == c_pkg_names[0]
    assert pkgs_found[0][1]


def test_check_already_exists_doesnt_add(mocker):
    c_pkg_names = (CCPkgName("mypack", "1.0", "py38_0_hblah"),)
    shared_config = {
        "destination-channel": "mock-channel",
        "labels": ["test"],
        "upload-channel": "blah-forge",
    }

    subprocess_mock = mocker.Mock()
    subprocess_mock.return_value = dedent(
        """
    {
      "mypack": [
        {
          "build": "py38_0_hblah",
          "build_number": 0,
          "name": "mypack",
          "version": "1.0"
        },
        {
          "build": "py38_0_hblah",
          "build_number": 0,
          "name": "mypack",
          "version": "0.9"
        }
      ]
    }
    """
    ).encode()
    mocker.patch("subprocess.check_output", new=subprocess_mock)

    pkgs_found = check_already_exists(c_pkg_names, shared_config)

    subprocess_mock.assert_called_once_with(
        [
            "conda",
            "search",
            "--json",
            "--full-name",
            "--override-channels",
            "--channel",
            "blah-forge",
            "--channel",
            "blah-forge/label/test",
            "mypack",
        ]
    )

    assert len(pkgs_found) == 1
    assert pkgs_found[0][0] == c_pkg_names[0]
    assert pkgs_found[0][1]


def test_check_already_exists_not_found(mocker):
    c_pkg_names = (CCPkgName("mypack", "1.0", "py38_0_hblah"),)
    shared_config = {
        "destination-channel": "mock-channel",
        "labels": ["test"],
        "upload-channel": "blah-forge",
    }

    output = dedent(
        """
        The following packages are not available from current channels:

          - ilastik-launch

        Current channels:

          - https://conda.anaconda.org/mock_channel/osx-64
          - https://conda.anaconda.org/mock_channel/noarch

        To search for alternate channels that may provide the conda package you're
        looking for, navigate to

            https://anaconda.org

        and use the search bar at the top of the page.

        Traceback (most recent call last):
          File "/Users/user/mambaforge/bin/publish-conda-stack", line 10, in <module>
            sys.exit(main())
          File "/Users/user/mambaforge/lib/python3.9/site-packages/publish_conda_stack/core.py", line 227, in main
            raise e
          File "/Users/user/mambaforge/lib/python3.9/site-packages/publish_conda_stack/core.py", line 223, in main
            status = build_and_upload_recipe(spec, shared_config, conda_bld_config)
          File "/Users/user/mambaforge/lib/python3.9/site-packages/publish_conda_stack/core.py", line 390, in build_and_upload_recipe
            packages_found = check_already_exists(c_pkg_names, shared_config)
          File "/Users/user/mambaforge/lib/python3.9/site-packages/publish_conda_stack/core.py", line 527, in check_already_exists
            search_results_text = subprocess.check_output(search_cmd).decode()
          File "/Users/user/mambaforge/lib/python3.9/subprocess.py", line 424, in check_output
            return run(*popenargs, stdout=PIPE, timeout=timeout, check=True,
          File "/Users/user/mambaforge/lib/python3.9/subprocess.py", line 528, in run
            raise CalledProcessError(retcode, process.args,
        subprocess.CalledProcessError: Command '['mamba', 'search', '--json', '--full-name', '--override-channels', '--channel', 'mock_channel', 'mypack']' returned non-zero exit status 1.
    """
    ).encode()

    mock_error = subprocess.CalledProcessError(
        returncode=1,
        cmd="['mamba', 'search', '--json', '--full-name', '--override-channels', '--channel', 'ilastik-forge', 'ilastik-launch']",
        output=output,
    )

    subprocess_mock = mocker.Mock(side_effect=mock_error)
    mocker.patch("subprocess.check_output", new=subprocess_mock)

    pkgs_found = check_already_exists(c_pkg_names, shared_config)

    subprocess_mock.assert_called_once_with(
        [
            "conda",
            "search",
            "--json",
            "--full-name",
            "--override-channels",
            "--channel",
            "blah-forge",
            "--channel",
            "blah-forge/label/test",
            "mypack",
        ]
    )

    assert len(pkgs_found) == 1
    assert pkgs_found[0][0] == c_pkg_names[0]
    assert not pkgs_found[0][1]
