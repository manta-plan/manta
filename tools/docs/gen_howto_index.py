# SPDX-FileCopyrightText: 2026 Manta contributors
#
# SPDX-License-Identifier: MIT

"""Write the table of guides in `docs/howto/index.md` from the front matter of each guide."""

from pathlib import Path

import yaml

FOLDER = Path(__file__).parents[2] / "docs" / "howto"
BEGIN = "<!-- howto-guides:begin -->\n"
END = "<!-- howto-guides:end -->\n"
HEADER = "| Guide | For | Use it to |\n| --- | --- | --- |\n"


def row(page: Path) -> str:
    _, front_matter, body = page.read_text(encoding="utf-8").split("---\n", 2)
    meta = yaml.safe_load(front_matter)
    title = next(line for line in body.splitlines() if line.startswith("# "))
    return f"| [{title[2:]}]({page.name}) | {', '.join(meta['tags'])} | {meta['description']} |\n"


def main() -> None:
    index = FOLDER / "index.md"
    before, rest = index.read_text(encoding="utf-8").split(BEGIN)
    after = rest.split(END)[1]
    guides = sorted(page for page in FOLDER.glob("*.md") if page != index)
    table = HEADER + "".join(row(page) for page in guides)
    index.write_text(f"{before}{BEGIN}\n{table}\n{END}{after}", encoding="utf-8")


if __name__ == "__main__":
    main()
