#!/usr/bin/env python
# PYTHON_ARGCOMPLETE_OK
from . import __version__
from .util import strip_label, labels_to_search_string, labels_to_upload_string

from os.path import basename, splitext, abspath, exists, dirname, normpath, isabs
from pathlib import Path
import argparse
import conda_build.api
import datetime
import json
import logging
import os
import subprocess
import sys
import tempfile
import time
import typing
import yaml


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
            specs_file_contents = yaml.safe_load(open(parsed_args.recipe_specs_path, "r"))
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
    specs_file_contents = yaml.safe_load(open(args.recipe_specs_path, "r"))

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
    shared_config["source-channel-string"] = " ".join(
        [f"-c {ch}" for ch in shared_config["source-channels"]]
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
    master_conda_build_config = None
    if (
        "master-conda-build-config" in shared_config
        and shared_config["master-conda-build-config"] != ""
    ):
        master_conda_build_config = shared_config["master-conda-build-config"]

        # make path to config file absolute (relative to specs file directory):
        if not isabs(master_conda_build_config):
            master_conda_build_config = specs_dir / master_conda_build_config
            shared_config["master-conda-build-config"] = str(master_conda_build_config)

    shared_config["labels"] = args.label

    destination_channel, label = strip_label(shared_config["destination-channel"])
    if label is not None:
        if label not in shared_config["labels"]:
            shared_config["labels"].append(label)
    shared_config["upload-channel"] = destination_channel

    if args.token != "":
        shared_config["token-string"] = f"-t {args.token}"
    else:
        shared_config["token-string"] = ""

    return shared_config, selected_recipe_specs, master_conda_build_config


def main():
    start_time = datetime.datetime.now()
    args = parse_cmdline_args()
    conda_bld_config = conda_build.api.get_or_merge_config(conda_build.api.Config())

    shared_config, selected_recipe_specs, master_conda_build_config = parse_specs(args)

    if args.list:
        print_recipe_list(selected_recipe_specs)
        sys.exit(0)

    tmp_args = vars(args)
    tmp_args["token"] = "nope"
    result = {
        "version": __version__,
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
            status = build_and_upload_recipe(
                spec, shared_config, conda_bld_config, master_conda_build_config
            )
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

    print("--------")
    print(f"DONE, Result written to {result_file}")
    print("--------")
    print("Summary:")
    print(yaml.dump(result, default_flow_style=False))


def write_result(result_file_name, result):
    result["last_updated"] = datetime.datetime.now().isoformat(timespec="seconds")
    with open(result_file_name, "w") as f:
        yaml.dump(result, f, default_flow_style=False)


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
    recipe_spec, shared_config, conda_bld_config: conda_build.api.Config, variant_config
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
    recipe_version, recipe_build_string = get_rendered_version(
        package_name, recipe_subdir, build_environment, shared_config, variant_config
    )
    logger.info(
        f"Recipe version is: {package_name}-{recipe_version}-{recipe_build_string}"
    )

    # Check our channel.  Did we already upload this version?
    package_info = {
        "pakage_name": package_name,
        "recipe_version": recipe_version,
        "recipe_build_string": recipe_build_string,
    }
    if check_already_exists(
        package_name, recipe_version, recipe_build_string, shared_config
    ):
        logger.info(
            f"Found {package_name}-{recipe_version}-{recipe_build_string} on {shared_config['destination-channel']}, skipping build."
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
            variant_config,
        )
        package_info["build-duration"] = time.time() - t0
        upload_package(
            package_name,
            recipe_version,
            recipe_build_string,
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
    package_name, recipe_subdir, build_environment, shared_config, variant_config
):
    """
    Use 'conda render' to process a recipe's meta.yaml (processes jinja templates and selectors).
    Returns the version and build string from the rendered file.

    Returns
        tuple: recipe_version, recipe_build_string
    """
    logger.info(f"Rendering recipe in {recipe_subdir}...")
    temp_meta_file = tempfile.NamedTemporaryFile(delete=False)
    temp_meta_file.close()
    render_cmd = (
        "conda render"
        f" {recipe_subdir}"
        f" {shared_config['source-channel-string']}"
        f" --file {temp_meta_file.name}"
        " --output"
    )
    if variant_config is not None:
        render_cmd = render_cmd + f" -m {variant_config}"

    logger.info(render_cmd)
    rendered_filename = subprocess.check_output(
        render_cmd, env=build_environment, shell=True
    ).decode()
    build_string_with_hash = rendered_filename.split("-")[-1].split(".tar.bz2")[0]

    meta = yaml.safe_load(open(temp_meta_file.name, "r"))
    os.remove(temp_meta_file.name)

    if meta["package"]["name"] != package_name:
        raise RuntimeError(
            f"Recipe for package '{package_name}' has unexpected name: '{meta['package']['name']}'"
        )

    return meta["package"]["version"], build_string_with_hash


def check_already_exists(
    package_name, recipe_version, recipe_build_string, shared_config
):
    """
    Check if the given package already exists on anaconda.org in the
    <destination> channel, including labels with the given version and build
    string.
    """
    logger.info(f"Searching channel: {shared_config['destination-channel']}")
    search_cmd = (
        f"conda search --json  --full-name --override-channels"
        f" --channel={shared_config['upload-channel']}"
        f" {labels_to_search_string(shared_config['upload-channel'], shared_config['labels'])}"
        f" {package_name}"
    )
    logger.info(search_cmd)
    try:
        search_results_text = subprocess.check_output(search_cmd, shell=True).decode()
    except Exception:
        # In certain scenarios, the search can crash.
        # In such cases, the package wasn't there anyway, so return False
        return False

    search_results = json.loads(search_results_text)

    if package_name not in search_results:
        return False

    for result in search_results[package_name]:
        if (
            result["build"] == recipe_build_string
            and result["version"] == recipe_version
        ):
            logger.info("Found package!")
            return True
    return False


def build_recipe(
    package_name,
    recipe_subdir,
    build_flags,
    build_environment,
    shared_config,
    variant_config,
):
    """
    Build the recipe.
    """
    logger.info(f"Building {package_name}")
    build_cmd = (
        f"conda build {build_flags}"
        f" {shared_config['source-channel-string']}"
        f" {recipe_subdir}"
    )
    if variant_config is not None:
        build_cmd = build_cmd + f" -m {variant_config}"

    logger.info(build_cmd)
    try:
        subprocess.check_call(build_cmd, env=build_environment, shell=True)
    except subprocess.CalledProcessError as ex:
        sys.exit(f"Failed to build package: {package_name}")


def upload_package(
    package_name,
    recipe_version,
    recipe_build_string,
    shared_config: typing.Dict,
    conda_bld_config: conda_build.api.Config,
):
    """
    Upload the package to the <destination> channel.
    """
    pkg_file_name = f"{package_name}-{recipe_version}-{recipe_build_string}.tar.bz2"
    BUILD_PKG_DIR = conda_bld_config.build_folder
    CONDA_PLATFORM = f"{conda_bld_config.platform}-{conda_bld_config.arch}"
    pkg_file_path = os.path.join(BUILD_PKG_DIR, CONDA_PLATFORM, pkg_file_name)
    if not os.path.exists(pkg_file_path):
        # Maybe it's a noarch package?
        pkg_file_path = os.path.join(BUILD_PKG_DIR, "noarch", pkg_file_name)
    if not os.path.exists(pkg_file_path):
        raise RuntimeError(f"Can't find built package: {pkg_file_name}")

    upload_cmd = (
        f"anaconda {shared_config['token-string']} upload -u {shared_config['upload-channel']}"
        f" {labels_to_upload_string(shared_config['labels'])} "
        f"{pkg_file_path}"
    )
    logger.info(f"Uploading {pkg_file_name}")
    try:
        subprocess.check_call(upload_cmd, shell=True)
    except subprocess.CalledProcessError as e:
        # clean up token string in case of errors
        if shared_config["token-string"] != "":
            e.cmd = e.cmd.replace(
                shared_config["token-string"], "<token-string removed>"
            )
        raise
