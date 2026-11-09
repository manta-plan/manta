<!--
SPDX-FileCopyrightText: Manta contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# Installation

Manta has no public release yet, so you run it from a clone of the repository.
Each page below installs only what one kind of work needs, so pick the row that matches yours.

| You want to                                  | Page                                            | You need                                                      | Docker |
| -------------------------------------------- | ----------------------------------------------- | ------------------------------------------------------------- | ------ |
| Use the whole web app in your browser        | [Full stack](full-stack.md)                     | Docker, uv, Node.js and pnpm                                  | yes    |
| Write or run blocks and playbooks            | [Blocks and playbooks](blocks-and-playbooks.md) | pixi, and uv to work on the `playbook` framework alone        | no     |
| Work on the REST API                         | [Backend](backend.md)                           | Docker and uv                                                 | yes    |
| Work on the web app with live reloading      | [Frontend](frontend.md)                         | Node.js and pnpm, and the backend setup                       | yes    |
