from publish_conda_stack.core import upload_package
import os
import pytest
import subprocess


@pytest.mark.parametrize(
    "label_string,token_string",
    [("--label main", ""), ("--label test --label staging", "-t abc")],
)
def test_upload(mocker, label_string, token_string):
    # Mocking:
    mocker.patch("subprocess.check_call")
    mocker.patch("os.path.exists")
    os.path.exists.return_value = True

    test_channel = "test_channel"
    build_folder = "/some/folder"
    platform = "linux"
    arch = "64"

    package_name = "test_package"
    recipe_version = "0.1.0"
    recipe_build_string = "py_1"
    shared_config = {
        "destination-channel": test_channel,
        "label-string": label_string,
        "token-string": token_string,
    }
    conda_bld_config = mocker.Mock(
        build_folder=build_folder, platform=platform, arch=arch
    )
    upload_package(
        package_name,
        recipe_version,
        recipe_build_string,
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
    label_string = "--label blah"
    token_string = "-t ohoh"
    test_channel = "test_channel"
    build_folder = "/some/folder"
    platform = "linux"
    arch = "64"

    package_name = "test_package"
    recipe_version = "0.1.0"
    recipe_build_string = "py_1"
    shared_config = {
        "destination-channel": test_channel,
        "label-string": label_string,
        "token-string": token_string,
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
            package_name,
            recipe_version,
            recipe_build_string,
            shared_config,
            conda_bld_config,
        )
    except subprocess.CalledProcessError as e:
        assert token_string not in e.cmd
    else:
        assert False, "Expected subprocess.CalledProcessError!!!"
