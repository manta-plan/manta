// SPDX-FileCopyrightText: Manta contributors
//
// SPDX-License-Identifier: Apache-2.0

import { DraftChangeDialog } from "./draft-change-dialog";
import { DraftEntityDialog } from "./draft-entity-dialog";
import { DraftScenarioDialog } from "./draft-scenario-dialog";

// The dialogs that make and change draft scenarios, mounted once by the
// project layout on Build and Inspect (the Scenarios panel and the toolbar open them).
export function ScenarioDialogs() {
  return (
    <>
      <DraftScenarioDialog />
      <DraftChangeDialog />
      <DraftEntityDialog />
    </>
  );
}
