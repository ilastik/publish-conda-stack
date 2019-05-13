[![Build Status](https://travis-ci.org/ilastik/ilastik-publish-packages.svg?branch=master)](https://travis-ci.org/ilastik/ilastik-publish-packages)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/ambv/black)

# publish-conda-stack

Scripts build a custom set of conda packages from a common environment and publish to a custom conda channel.

## Introduction:

Originally developed to manage the dependency tree for [ilastik](https://ilastik.org), which we handle by using the _conda package manager_.
The build process is automated by the scripts in this repository.

## Installation

```bash
conda install -n base -c ilastik-forge -c conda-forge publish-conda-stack
```

This also installs the `publish-conda-stack` main entry-point and makes it available in the respective conda environment.

## Building packages:

### Configuration files

Run `conda install anaconda-client`. You need to be logged in to your https://anaconda.org account by running `anaconda login`.

`publish-conda-stack` builds packages specified in a `yaml` config file. An example:

#### Common configuration

```yaml
# common configuration for all packages defined in shared-config:
shared-config:
  # will translate to --python for every conda-build, deprecated, use pin-file
  python: '3.6'
  # will translate to --numpy for every conda-build, deprecated, use pin-file
  numpy: '1.13'
  # Path to store git repositories containing recipes. Relative to this yaml file's directory.
  repo-cache-dir: ./repo-cache
  # Optional path to master conda_build_config file to unify build-environment and package pins across recipes
  master-conda-build-config: ./my-pins.yaml
  # Channels to check for dependencies of the built package
  source-channels:
    - my-personal-channel
    - conda-forge
  # channel to upload recipes to
  destination-channel: my-personal-channel
```

#### Package definitions

```yaml
recipe-specs:
    - name: PACKAGE_NAME
      recipe-repo: PACKAGE_RECIPE_GIT_URL
      tag: RECIPE_GIT_TAG_OR_BRANCH
      recipe-subdir: RECIPE_DIR_IN_GIT_REPO
      
      # Optional specs
      environment:
          MY_VAR: VALUE
      conda-build-flags: STRING_THAT_WILL_BE_APPENDED_TO_CONDA_BUILD
      # by default a package is built on all 3 platforms, you can restrict that by specifying the following
      build-on:
        - linux
        - win
        - osx

    - name: NEXT_PACKAGE
          ...
```

#### Optional Master conda-build-config

You can add a master `conda_build_config.yaml` file that will be passed to `conda-build`, hence, it supports all syntax as described in the [`conda-build` docs](https://docs.conda.io/projects/conda-build/en/latest/source/variants.html).
This field is optional.
If the field is left blank, it will be simply ignored.

Example file:

```yaml
- python: 3.6

pin_run_as_build:
  python: x.x
```

### Building

```bash
# on Linux and Windows:
publish-conda-stack my-recipe-specs.yaml
# on Mac:
MACOSX_DEPLOYMENT_TARGET=10.9 publish-conda-stack my-recipe-specs.yaml
```

The `build-recipes.py` script parses the packages from `my-recipe-specs.yaml`, and for each package checks whether an up-to-date version is already available on the `destination-channel` listed in `my-recipe-specs.yaml`.  If the packages don't yet exist in that channel set, it will build the package and upload it.