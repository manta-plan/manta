<!--
SPDX-FileCopyrightText: datarecord contributors

SPDX-License-Identifier: CC-BY-4.0
-->

# Installation

## Installing a user environment

!!! hint

    If it is your first time using Python, we recommend [pixi](https://pixi.prefix.dev/), [conda](https://docs.conda.io/projects/conda), or [uv](https://docs.astral.sh/uv/) as easy-to-use package managers.
    They are available for Windows, macOS, and GNU/Linux.
    It is always helpful to use dedicated environments.

You can install `datarecord` via all common package managers:

=== "pixi"

    ``` bash
    pixi add --pypi datarecord
    ```

=== "uv"

    ``` bash
    uv add datarecord
    ```

=== "conda"

    ``` bash
    conda create -n datarecord "python>=3.12" "pip"
    conda activate datarecord
    pip install datarecord
    ```

=== "pip"

    ``` bash
    pip install datarecord
    ```

`datarecord` is written and tested to be compatible with Python 3.12 and above.
We recommend to use the latest version with active support (see [endoflife.date](https://endoflife.date/python)).

## Installing a development environment

The install instructions are slightly different to create a development environment compared to a user environment:

--8<-- "README.md:docs-install-dev"

For more detailed instructions specific to developing the `datarecord` codebase, see the [contributing guide](contributing.md).
