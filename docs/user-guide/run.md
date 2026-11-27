<!--
SPDX-FileCopyrightText: Manta contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# Start and follow a run

This guide shows how to start a run of a [playbook](playbooks.md) in the web app, and follow its status and log.
You need a Manta account, the web address of your Manta app, and a project with a copy of the data record you want to run on.

!!! note "What the web app supports today"

    A run starts from the input model of a data record, not from a scenario.
    Manta refuses a run on a data record that the project has no copy of.
    Manta can create an **Example project** for you when you first sign in, with a copy of each example data record.
    A project you create in the web app has no copies.
    The web app shows the status and the log of the whole run, not of each block, and does not show the models a run produced.

## Sign in

1. Open Manta in your browser. The sign-in page opens.
2. Enter your username and password, then select **Log In**.

The **Projects** page opens.
To sign out, select **Log out** in the top right corner of the **Projects** page.

## Open the Run tab

1. On the **Projects** page, select the project. Its **Model** tab opens.
2. Select the **Run** tab at the top of the page.

The **Runs** page opens, with the runs of this project.

## Start a run

1. Select **New run**. The **Create a new run** dialog opens.
2. In **Data record**, pick the data record to run on.
3. In **Playbook**, pick a playbook. The canvas shows its steps from left to right, set to the playbook's default settings.
4. If the playbook has global settings, such as **Expansion Mode**, pick a value for each under **Playbook**. The canvas shows only the steps that run with these values.
5. To change the settings of a step, select the step on the canvas, then edit its settings below the canvas.
6. Select **Create run**.

Manta checks the settings before it starts the run.
If it finds problems, the dialog lists every one of them, so you can fix them and select **Create run** again.
To start again from the playbook's defaults, select **Use playbook defaults**.
Once the settings pass the check, Manta starts the run and adds it to the **Recent runs** table.

## Follow a run

The **Recent runs** table lists each run with its status and the time it started.
The counters above the table show how many runs the project has, and how many are running, completed, or scheduled.

Manta runs a limited number of playbooks at once.
A run started beyond that number has the status **Queued**, and starts once another run finishes.
While a run in the table is not finished, the statuses update on their own.

Manta also limits how long a run may take.
A run that takes longer is stopped and has the status **Timed Out**, which tells it from a run that **Failed** for another reason.

- To see the latest status of every run right away, select **Refresh**.
- To list only runs with certain statuses, pick them from the **All statuses** list above the table.
- To find one run, enter its run UUID, a long identifier shown in its details, in the search box.

## Read the log of a run

1. In the **Recent runs** table, select the arrow in the **Actions** column of the run. Its details open below it.
2. Read the run UUID, the project UUID, the status, and the log of the run.
3. To fetch the latest log, select **Refresh** in the details.

The log lists the messages of the whole run in the order the run wrote them.
