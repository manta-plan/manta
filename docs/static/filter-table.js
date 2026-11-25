/*
 * SPDX-FileCopyrightText: Manta contributors
 *
 * SPDX-License-Identifier: MIT
 */

const FILTER_COLUMN = 1;
const ALL = "All";

function cellValues(row) {
  return row.cells[FILTER_COLUMN].textContent.split(",").map((value) => value.trim());
}

function addFilter(wrapper) {
  if (wrapper.querySelector(".filter-table__buttons")) return;
  const rows = [...wrapper.querySelectorAll("tbody tr")];
  const bar = document.createElement("p");
  bar.className = "filter-table__buttons";
  for (const option of [ALL, ...[...new Set(rows.flatMap(cellValues))].sort()]) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "md-button";
    button.textContent = option;
    button.addEventListener("click", () => {
      for (const other of bar.children) {
        other.classList.toggle("md-button--primary", other === button);
        other.setAttribute("aria-pressed", String(other === button));
      }
      for (const row of rows) {
        row.hidden = option !== ALL && !cellValues(row).includes(option);
      }
    });
    bar.append(button);
  }
  wrapper.prepend(bar);
  bar.firstElementChild.click();
}

document$.subscribe(() => document.querySelectorAll(".filter-table").forEach(addFilter));
