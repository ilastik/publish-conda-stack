from publish_conda_stack.core import get_rendered_version, upload_package, CCPkgName
from publish_conda_stack.util import labels_to_upload_string
import os
import pytest
import subprocess


@pytest.mark.parametrize(
    "labels,token_string", [(["main"], ""), (["test", "staging"], "-t abc")]
)
def test_upload(mocker, labels, token_string):
    # Mocking:
    mocker.patch("subprocess.check_call")
    mocker.patch("os.path.exists")
    os.path.exists.return_value = True

    test_channel = "test_channel"
    label_string = labels_to_upload_string(labels)
    build_folder = "/some/folder"
    platform = "linux"
    arch = "64"

    package_name = "test_package"
    recipe_version = "0.1.0"
    recipe_build_string = "py_1"

    c_pkg_names = (CCPkgName(package_name, recipe_version, recipe_build_string),)

    shared_config = {
        "destination-channel": test_channel,
        "labels": labels,
        "token-string": token_string,
        "upload-channel": test_channel,
    }
    conda_bld_config = mocker.Mock(
        build_folder=build_folder, platform=platform, arch=arch
    )
    upload_package(
        c_pkg_names,
        shared_config,
        conda_bld_config,
    )

    test_path = os.path.join(
        build_folder,
        f"{platform}-{arch}",
        f"{package_name}-{recipe_version}-{recipe_build_string}.tar.bz2",
    )
    assert os.path.exists.call_count == 2
    subprocess.check_call.assert_called_once_with(
        f"anaconda {token_string} upload -u {test_channel} {label_string} {test_path}",
        shell=True,
    )


def test_hide_token(mocker):
    labels = ["blah"]
    label_string = labels_to_upload_string(labels)
    token_string = "-t ohoh"
    test_channel = "test_channel"
    build_folder = "/some/folder"
    platform = "linux"
    arch = "64"

    package_name = "test_package"
    recipe_version = "0.1.0"
    recipe_build_string = "py_1"

    c_pkg_names = (CCPkgName(package_name, recipe_version, recipe_build_string),)

    shared_config = {
        "destination-channel": test_channel,
        "labels": labels,
        "token-string": token_string,
        "upload-channel": test_channel,
    }
    conda_bld_config = mocker.Mock(
        build_folder=build_folder, platform=platform, arch=arch
    )

    test_path = os.path.join(
        build_folder,
        f"{platform}-{arch}",
        f"{package_name}-{recipe_version}-{recipe_build_string}.tar.bz2",
    )
    cmd = f"anaconda {token_string} upload -u {test_channel} {label_string} {test_path}"

    def side_effect(callable_str, *args, **kwargs):
        raise subprocess.CalledProcessError(cmd=callable_str, returncode=1)

    # Mocking:
    mocker.patch("subprocess.check_call")
    mocker.patch("os.path.exists")
    subprocess.check_call.side_effect = side_effect
    os.path.exists.return_value = True

    try:
        upload_package(
            c_pkg_names,
            shared_config,
            conda_bld_config,
        )
    except subprocess.CalledProcessError as e:
        assert token_string not in e.cmd
    else:
        assert False, "Expected subprocess.CalledProcessError!!!"


def test_upload_channel(mocker):
    # Mocking:
    mocker.patch("subprocess.check_call")
    mocker.patch("os.path.exists")
    os.path.exists.return_value = True

    arch = "64"
    build_folder = "/some/folder"
    labels = ["blah"]
    label_string = labels_to_upload_string(labels)
    platform = "linux"
    test_channel = "test_channel"
    token_string = ""

    package_name = "test_package"
    recipe_build_string = "py_1"
    recipe_version = "0.1.0"

    c_pkg_names = (CCPkgName(package_name, recipe_version, recipe_build_string),)
    shared_config = {
        "destination-channel": f"{test_channel}/label/blah",
        "labels": labels,
        "token-string": token_string,
        "upload-channel": test_channel,
    }
    conda_bld_config = mocker.Mock(
        build_folder=build_folder, platform=platform, arch=arch
    )

    upload_package(
        c_pkg_names,
        shared_config,
        conda_bld_config,
    )

    test_path = os.path.join(
        build_folder,
        f"{platform}-{arch}",
        f"{package_name}-{recipe_version}-{recipe_build_string}.tar.bz2",
    )
    assert os.path.exists.call_count == 2
    subprocess.check_call.assert_called_once_with(
        f"anaconda {token_string} upload -u {test_channel} {label_string} {test_path}",
        shell=True,
    )


def test_upload_multiple(mocker):
    # Mocking:
    mocker.patch("subprocess.check_call")
    mocker.patch("os.path.exists")
    os.path.exists.return_value = True

    arch = "64"
    build_folder = "/some/folder"
    labels = ["blah"]
    label_string = labels_to_upload_string(labels)
    platform = "linux"
    test_channel = "test_channel"
    token_string = ""

    package_name = "test_package"
    recipe_build_string = "py_1"
    recipe_version = "0.1.0"

    c_pkg_names = (
        CCPkgName(package_name, recipe_version, recipe_build_string),
        CCPkgName(package_name, recipe_version, "py_2"),
    )

    shared_config = {
        "destination-channel": f"{test_channel}/label/blah",
        "labels": labels,
        "token-string": token_string,
        "upload-channel": test_channel,
    }
    conda_bld_config = mocker.Mock(
        build_folder=build_folder, platform=platform, arch=arch
    )

    upload_package(
        c_pkg_names,
        shared_config,
        conda_bld_config,
    )

    test_paths = [
        os.path.join(
            build_folder,
            f"{platform}-{arch}",
            f"{c_pkg_name.package_name}-{c_pkg_name.version}-{c_pkg_name.build_string}.tar.bz2",
        )
        for c_pkg_name in c_pkg_names
    ]

    assert os.path.exists.call_count == 2 * len(test_paths)

    subprocess.check_call.assert_called_once_with(
        f"anaconda {token_string} upload -u {test_channel} {label_string} {' '.join(test_paths)}",
        shell=True,
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
