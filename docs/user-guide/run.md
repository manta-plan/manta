<!--
SPDX-FileCopyrightText: Manta contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# Start and follow a run

This guide shows how to start a run in the web app and follow its status and log.
You need a Manta account and the web address of your Manta app.

!!! note "What the web app supports today"

    The web app runs only the `expand` playbook, with its default settings.
    You cannot pick another playbook, change its settings, or choose a model or a scenario.
    Because the run has no model to work on, it does not complete.
    The web app shows the status and the log of the whole run, not of each block, and does not show the models a run produced.

## Sign in

1. Open Manta in your browser. The sign-in page opens.
2. Enter your username and password, then select **Sign in**.

The **Runs** page opens.
To sign out, select **Sign out** in the top right corner.

## Start a run

Select **New run**.
Manta starts a run of the `expand` playbook and adds it to the **Recent runs** table.

The first time you start a run in a browser tab, Manta creates a project for it.
The **Runs** page lists only the runs of that project, so a run you started in another tab or window does not appear.

## Follow a run

The **Recent runs** table lists each run with its status and the time it started.
The counters above the table show how many runs the project has, and how many are running, completed or scheduled.

- To see the latest status of every run, select **Refresh**.
- To list only runs with certain statuses, pick them from the **All statuses** list above the table.
- To find one run, enter its run UUID, a long identifier shown in its details, in the search box.

## Read the log of a run

1. In the **Recent runs** table, select the arrow in the **Actions** column of the run. Its details open below it.
2. Read the run UUID, the project UUID, the status and the log of the run.
3. To fetch the latest log, select **Refresh** in the details.

The log lists the messages of the whole run in the order the run wrote them.
