#!/usr/bin/env python
# PYTHON_ARGCOMPLETE_OK
import argparse
import datetime
import json
import logging
import os
import subprocess
import sys
import time
from collections import namedtuple
from itertools import chain
from os.path import abspath, basename, dirname, exists, isabs, normpath, splitext
from pathlib import Path
from typing import Dict, List, Tuple

import conda_build.api
from ruamel.yaml import YAML

from . import __version__
from .cmdutil import CondaCommand, conda_cmd_base
from .util import labels_to_upload_string, strip_label

logger = logging.getLogger()
logging.basicConfig(format="%(levelname)s: %(message)s", level=logging.INFO)

try:
    import argcomplete
    from argcomplete.completers import FilesCompleter

    ENABLE_TAB_COMPLETION = True
except Exception as e:
    # See --help text for instructions.
    ENABLE_TAB_COMPLETION = False
    logger.debug(f"Tab completion not available: {e}")


# Disable git pager for log messages, etc.
os.environ["GIT_PAGER"] = ""

# Canonical Conda Package Name
CCPkgName = namedtuple("CCPkgName", ["package_name", "version", "build_string"])


def parse_cmdline_args():
    """
    Parse the user's command-lines, with support for tab-completion.
    """
    prog_name = sys.argv[0]
    if prog_name[0] not in (".", "/"):
        prog_name = "./" + prog_name

    parser = argparse.ArgumentParser(
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "-l",
        "--list",
        action="store_true",
        help="List the recipe names in the specs file",
    )
    specs_path_arg = parser.add_argument(
        "recipe_specs_path", help="Path to a recipe specs YAML file"
    )
    selection_arg = parser.add_argument(
        "selected_recipes",
        nargs="*",
        help="Which recipes to process (Default: process all)",
    )
    parser.add_argument(
        "--start-from",
        default=os.environ.get("PUBLISH_START_FROM", ""),
        help="Recipe name to start from building recipe specs in YAML file.",
    )
    parser.add_argument(
        "--label",
        action="append",
        default=[],
        help="Use label(s) when uploading package. Can be added multiple times.",
    )
    parser.add_argument("--token", default="", help="Token used for anaconda upload.")
    parser.add_argument(
        "--logfile",
        "-o",
        default="",
        help=(
            "Specify custom output path of the log/summary yaml file, "
            "or a directory in which to store it with an auto-chosen name."
        ),
    )

    if ENABLE_TAB_COMPLETION:

        def complete_recipe_selection(prefix, action, parser, parsed_args):
            yaml = YAML(typ="safe")
            specs_file_contents = yaml.load(open(parsed_args.recipe_specs_path, "r"))
            recipe_specs = specs_file_contents["recipe-specs"]
            names = (spec["name"] for spec in recipe_specs)
            return filter(lambda name: name.startswith(prefix), names)

        specs_path_arg.completer = FilesCompleter((".yml", ".yaml"), directories=False)
        selection_arg.completer = complete_recipe_selection
        argcomplete.autocomplete(parser)

    args = parser.parse_args()
    return args


def parse_specs(args):

    specs_dir = Path(dirname(abspath(args.recipe_specs_path)))
    yaml = YAML(typ="safe")
    specs_file_contents = yaml.load(open(args.recipe_specs_path, "r"))

    # Read the 'shared-config' section
    shared_config = specs_file_contents["shared-config"]
    required_shared_config_keys = [
        "source-channels",
        "destination-channel",
        "repo-cache-dir",
    ]
    assert all(
        k in shared_config for k in required_shared_config_keys
    ), f"shared-config section is missing expected keys.  Expected: {required_shared_config_keys}"

    # Convenience member
    shared_config["conda-source-channel-list"] = list(
        chain.from_iterable([("-c", ch) for ch in shared_config["source-channels"]])
    )

    # Overwrite repo-cache-dir with an absolute path
    # Path is given relative to the specs file directory.
    if not shared_config["repo-cache-dir"].startswith("/"):
        shared_config["repo-cache-dir"] = Path(
            normpath(specs_dir / shared_config["repo-cache-dir"])
        )

    os.makedirs(shared_config["repo-cache-dir"], exist_ok=True)

    selected_recipe_specs = get_selected_specs(
        args, specs_file_contents["recipe-specs"]
    )

    # Optional master_conda_build_config
    if (
        "master-conda-build-config" in shared_config
        and shared_config["master-conda-build-config"] != ""
    ):
        master_conda_build_config = shared_config["master-conda-build-config"]

        # make path to config file absolute (relative to specs file directory):
        if not isabs(master_conda_build_config):
            shared_config["master-conda-build-config"] = str(
                specs_dir / master_conda_build_config
            )
    else:
        shared_config["master-conda-build-config"] = None

    shared_config["labels"] = args.label

    destination_channel, label = strip_label(shared_config["destination-channel"])
    if label is not None:
        if label not in shared_config["labels"]:
            shared_config["labels"].append(label)
    shared_config["upload-channel"] = destination_channel

    if "backend" not in shared_config:
        shared_config["backend"] = "conda"

    shared_config["backend"] = shared_config["backend"].lower()
    if shared_config["backend"] not in ["conda", "mamba"]:
        raise ValueError(
            f"Backend must be either `conda` or `mamba` - found {shared_config['backend']}"
        )

    logger.info(
        f"Using `{shared_config['backend']}` backend. Can be set in config file under the 'backend' key."
    )

    if args.token != "":
        shared_config["token-string"] = f"-t {args.token}"
    else:
        shared_config["token-string"] = ""

    return shared_config, selected_recipe_specs


def main():
    start_time = datetime.datetime.now()
    args = parse_cmdline_args()
    conda_bld_config = conda_build.api.get_or_merge_config(conda_build.api.Config())

    shared_config, selected_recipe_specs = parse_specs(args)

    if args.list:
        print_recipe_list(selected_recipe_specs)
        sys.exit(0)

    tmp_args = vars(args)
    tmp_args["token"] = "nope"
    result = {
        "version": __version__,
        "backend": shared_config["backend"],
        "found": [],
        "built": [],
        "errors": [],
        "skipped": [],
        "start_time": start_time.isoformat(timespec="seconds"),
        "args": tmp_args,
    }

    default_outname = f"{start_time.strftime('%Y%m%d-%H%M%S')}_build_out.yaml"
    if os.path.isdir(args.logfile):
        logdir = os.path.abspath(args.logfile)
        result_file = os.path.join(logdir, default_outname)
    elif args.logfile:
        result_file = os.path.abspath(args.logfile)
    else:
        result_file = os.path.abspath(default_outname)

    for spec in selected_recipe_specs:
        try:
            status = build_and_upload_recipe(spec, shared_config, conda_bld_config)
        except Exception as e:
            result["errors"].append({"spec": spec, "error": e})
            write_result(result_file, result)
            raise e

        for k, v in status.items():
            result[k].append(v)
        write_result(result_file, result)

    end_time = datetime.datetime.now()
    result["end_time"] = end_time.isoformat(timespec="seconds")
    result["duration"] = str(end_time - start_time)
    write_result(result_file, result)

    yaml = YAML(typ="safe")
    yaml.default_flow_style = False
    print("--------")
    print(f"DONE, Result written to {result_file}")
    print("--------")
    print("Summary:")
    print(yaml.dump(result))


def write_result(result_file_name, result):
    result["last_updated"] = datetime.datetime.now().isoformat(timespec="seconds")
    yaml = YAML(typ="safe")
    yaml.default_flow_style = False
    with open(result_file_name, "w") as f:
        yaml.dump(result, f)


def print_recipe_list(recipe_specs):
    max_name = max(len(spec["name"]) for spec in recipe_specs)
    for spec in recipe_specs:
        logger.info(
            f"{spec['name']: <{max_name}} : {spec['recipe-repo']} ({spec['tag']})"
        )


def get_selected_specs(args, full_recipe_specs):
    """
    If the user gave a list of specific recipes to process,
    select them from the given recipe specs.

    Args:
        start_from (str): Name of the recipe from from full_recipe_specs to
          start from. If not '', then the recipe should be in full_recipe_specs.
        selected_recipes (list): List of recipe names to build
        full_recipe_specs (list): List of recipes, usually loaded from yaml

    Returns:
        list: list of recipes to build
    """
    available_recipe_names = [spec["name"] for spec in full_recipe_specs]
    if args.start_from != "":
        if args.start_from not in available_recipe_names:
            sys.exit(
                f"'start-from' parameter invalid: {args.start_from} not found in full_recipe_specs."
            )
        full_recipe_specs = full_recipe_specs[
            available_recipe_names.index(args.start_from) : :
        ]

    if not args.selected_recipes:
        return full_recipe_specs

    invalid_names = set(args.selected_recipes) - set(available_recipe_names)
    if invalid_names:
        sys.exit(
            "Invalid selection: The following recipes are not listed"
            f" in {args.recipe_specs_path}: {', '.join(invalid_names)}"
        )

    # Remove non-selected recipes
    filtered_specs = list(
        filter(lambda spec: spec["name"] in args.selected_recipes, full_recipe_specs)
    )
    filtered_names = [spec["name"] for spec in filtered_specs]
    if filtered_names != args.selected_recipes:
        logger.info(
            f"WARNING: Your recipe list was not given in the same order as in {args.recipe_specs_path}."
        )
        logger.info(
            f"         They will be processed in the following order: {', '.join(filtered_names)}"
        )

    return filtered_specs


def build_and_upload_recipe(
    recipe_spec, shared_config, conda_bld_config: conda_build.api.Config
):
    """
    Given a recipe-spec dictionary, build and upload the recipe if
    it doesn't already exist on <destination>.

    More specifically:
      1. Clone the recipe repo to our cache directory (if necessary)
      2. Check out the tag (with submodules, if any)
      3. Render the recipe's meta.yaml ('conda render')
      4. Query the <destination> channel for the exact package. This includes all labels, too
         e.g. if `--label debug` is specified this will also search <destination>/label/debug,
         and <destination>/label/main!.
         If a package with the same exact rendered package string is available under a different label,
         anaconda upload of this package will fail.
      5. If the package doesn't exist on <destination> channel yet, build it and upload it.

    A recipe-spec is a dict with the following keys:
      - name -- The package name
      - recipe-repo -- A URL to the git repo that contains the package recipe.
      - recipe-subdir -- The name of the recipe directory within the git repo
      - tag -- Which tag/branch/commit of the recipe-repo to use.
      - environment (optional) -- Extra environment variables to define before building the recipe
      - conda-build-flags (optional) -- Extra arguments to pass to conda build for this package
      - build-on (optional) -- A list of operating systems on which the package should be built. Available are: osx, win, linux
    """
    # Extract spec fields
    package_name = recipe_spec["name"]
    recipe_repo = recipe_spec["recipe-repo"]
    tag = recipe_spec["tag"]
    recipe_subdir = recipe_spec["recipe-subdir"]
    conda_build_flags = recipe_spec.get("conda-build-flags", "")
    conda_build_flags = conda_build_flags.split(" ") if conda_build_flags else []

    logger.info("-------------------------------------------")
    logger.info(f"Processing {package_name}")

    # check whether we need to build the package on this OS at all
    if "build-on" in recipe_spec:
        platforms_to_build_on = recipe_spec["build-on"]
        assert isinstance(platforms_to_build_on, list)
        assert all(o in ["win", "osx", "linux"] for o in platforms_to_build_on)
    else:
        platforms_to_build_on = ["win", "osx", "linux"]

    PLATFORM_STR = conda_bld_config.platform

    if PLATFORM_STR not in platforms_to_build_on:
        logger.info(
            f"Not building {package_name} on platform {PLATFORM_STR}, only builds on {platforms_to_build_on}"
        )
        return {"skipped": {"spec": recipe_spec}}

    # configure build environment
    build_environment = dict(**os.environ)
    if "environment" in recipe_spec:
        for key in recipe_spec["environment"].keys():
            recipe_spec["environment"][key] = str(recipe_spec["environment"][key])
        build_environment.update(recipe_spec["environment"])

    os.chdir(shared_config["repo-cache-dir"])
    repo_dir = checkout_recipe_repo(recipe_repo, tag)

    # All subsequent work takes place within the recipe repo
    os.chdir(repo_dir)
    # Render
    c_pkg_names = get_rendered_version(
        package_name, recipe_subdir, build_environment, shared_config
    )
    logger.info(
        f"Recipe rendered to {len(c_pkg_names)} packages: {['-'.join(map(str, x)) for x in c_pkg_names]}"
    )

    # Check our channel.  Did we already upload this version?
    package_info = {
        "pakage_name": package_name,
        "recipe_versions": [x.version for x in c_pkg_names],
        "recipe_build_string": [x.build_string for x in c_pkg_names],
    }

    packages_found = check_already_exists(c_pkg_names, shared_config)
    if all(x[1] for x in packages_found):
        logger.info(
            f"Found {c_pkg_names} on {shared_config['destination-channel']}, skipping build."
        )
        ret_dict = {"found": package_info}
    else:
        # Not on our channel.  Build and upload.
        t0 = time.time()
        build_recipe(
            package_name,
            recipe_subdir,
            conda_build_flags,
            build_environment,
            shared_config,
        )
        package_info["build-duration"] = time.time() - t0
        upload_package(
            c_pkg_names,
            shared_config,
            conda_bld_config,
        )
        ret_dict = {"built": package_info}
    return ret_dict


def checkout_recipe_repo(recipe_repo, tag):
    """
    Checkout the given repository and tag.
    Clone it first if necessary, and update any submodules it has.
    """
    try:
        repo_name = splitext(basename(recipe_repo))[0]

        cwd = abspath(os.getcwd())
        if not exists(repo_name):
            # assuming url of the form github.com/remote-name/myrepo[.git]
            remote_name = recipe_repo.split("/")[-2]
            subprocess.check_call(
                f"git clone -o {remote_name} {recipe_repo}", shell=True
            )
            os.chdir(repo_name)
        else:
            # The repo is already cloned in the cache,
            # but which remote do we want to fetch from?
            os.chdir(repo_name)
            remote_output = (
                subprocess.check_output("git remote -v", shell=True)
                .decode("utf-8")
                .strip()
            )
            remotes = {}
            for line in remote_output.split("\n"):
                name, url, role = line.split()
                remotes[url] = name

            if recipe_repo in remotes:
                remote_name = remotes[recipe_repo]
            else:
                # Repo existed locally, but was missing the desired remote.
                # Add it.
                remote_name = recipe_repo.split("/")[-2]
                subprocess.check_call(
                    f"git remote add {remote_name} {recipe_repo}", shell=True
                )

            subprocess.check_call(f"git fetch {remote_name}", shell=True)

        logger.info(f"Checking out {tag} of {repo_name} into {cwd}...")
        subprocess.check_call(f"git checkout {tag}", shell=True)
        subprocess.check_call(f"git pull --ff-only {remote_name} {tag}", shell=True)
        subprocess.check_call(f"git submodule update --init --recursive", shell=True)
    except subprocess.CalledProcessError:
        raise RuntimeError(
            f"Failed to clone or update the repository: {recipe_repo}\n"
            "Double-check the repo url, or delete your repo cache and try again."
        )

    logger.info(f"Recipe checked out at tag: {tag}")
    logger.info("Most recent commit:")
    subprocess.call("git log -n1", shell=True)
    os.chdir(cwd)

    return repo_name


def get_rendered_version(
    package_name,
    recipe_subdir,
    build_environment,
    shared_config,
) -> Tuple[CCPkgName, ...]:
    """
    Use 'conda render' to process a recipe's meta.yaml (processes jinja templates and selectors).
    Returns the version and build string from the rendered file.

    Returns
        tuple: recipe_version, recipe_build_string
    """
    logger.info(f"Rendering recipe in {recipe_subdir}...")
    render_cmd = conda_cmd_base(CondaCommand.RENDER, shared_config) + [recipe_subdir]
    logger.info(" ".join(render_cmd))
    subprocess_output = subprocess.check_output(
        render_cmd, env=build_environment
    ).decode()

    rendered_filenames = [
        x for x in subprocess_output.split() if x.endswith(".tar.bz2")
    ]
    name_version_builds = [
        CCPkgName(*Path(x).name.replace(".tar.bz2", "").rsplit("-", maxsplit=2))
        for x in rendered_filenames
    ]

    if not all(x.package_name == package_name for x in name_version_builds):
        raise RuntimeError(
            f"Expected all outputs to be {package_name}, but got"
            f"{name_version_builds}"
        )

    return tuple(name_version_builds)


def check_already_exists(
    c_pkg_names: Tuple[CCPkgName, ...], shared_config
) -> Tuple[Tuple[CCPkgName, bool], ...]:
    """
    Check if the given package already exists on anaconda.org in the
    <destination> channel, including labels with the given version and build
    string.
    """
    # assuming all packages have the same name
    package_name = c_pkg_names[0].package_name
    logger.info(f"Searching channel: {shared_config['destination-channel']}")
    search_cmd = conda_cmd_base(CondaCommand.SEARCH, shared_config) + [package_name]
    logger.info(" ".join(search_cmd))

    try:
        search_results_text = subprocess.check_output(search_cmd).decode()
    except subprocess.CalledProcessError as e:
        output = e.output.decode()
        if "following packages are not available from current channels" in output:
            search_results_text = r"{}"
        else:
            raise e

    search_results = json.loads(search_results_text)

    if package_name not in search_results:
        return tuple((c_pkg, False) for c_pkg in c_pkg_names)

    c_pkgs_found: List[Tuple[CCPkgName, bool]] = []
    for c_pkg_name in c_pkg_names:
        found = False
        for result in search_results[package_name]:
            if (
                result["build"] == c_pkg_name.build_string
                and result["version"] == c_pkg_name.version
            ):
                found = True
                logger.info(f"Found package {c_pkg_name}")
                break

        c_pkgs_found.append((c_pkg_name, found))

    return tuple(c_pkgs_found)


def build_recipe(
    package_name,
    recipe_subdir,
    build_flags,
    build_environment,
    shared_config,
):
    """
    Build the recipe.
    """
    logger.info(f"Building {package_name}")
    build_cmd = conda_cmd_base(CondaCommand.BUILD, shared_config)
    build_cmd.extend(build_flags)
    build_cmd.append(recipe_subdir)
    logger.info(" ".join(build_cmd))
    try:
        subprocess.check_call(build_cmd, env=build_environment)
    except subprocess.CalledProcessError as ex:
        sys.exit(f"Failed to build package: {package_name}")


def upload_package(
    c_pkg_names,
    shared_config: Dict,
    conda_bld_config: conda_build.api.Config,
):
    """
    Upload the package to the <destination> channel.
    """
    package_paths = []
    for c_pkg_name in c_pkg_names:
        pkg_file_name = f"{c_pkg_name.package_name}-{c_pkg_name.version}-{c_pkg_name.build_string}.tar.bz2"
        BUILD_PKG_DIR = conda_bld_config.build_folder
        CONDA_PLATFORM = f"{conda_bld_config.platform}-{conda_bld_config.arch}"
        pkg_file_path = os.path.join(BUILD_PKG_DIR, CONDA_PLATFORM, pkg_file_name)
        if not os.path.exists(pkg_file_path):
            # Maybe it's a noarch package?
            pkg_file_path = os.path.join(BUILD_PKG_DIR, "noarch", pkg_file_name)
        if not os.path.exists(pkg_file_path):
            raise RuntimeError(f"Can't find built package: {pkg_file_name}")

        package_paths.append(pkg_file_path)

    upload_cmd = (
        f"anaconda {shared_config['token-string']} upload --skip-existing -u {shared_config['upload-channel']}"
        f" {labels_to_upload_string(shared_config['labels'])} "
        f"{' '.join(package_paths)}"
    )
    logger.info(f"Uploading {package_paths}")
    try:
        subprocess.check_call(upload_cmd, shell=True)
    except subprocess.CalledProcessError as e:
        # clean up token string in case of errors
        if shared_config["token-string"] != "":
            e.cmd = e.cmd.replace(
                shared_config["token-string"], "<token-string removed>"
            )
        raise
