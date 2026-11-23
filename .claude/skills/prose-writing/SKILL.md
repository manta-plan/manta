---
# SPDX-FileCopyrightText: Manta contributors
# SPDX-License-Identifier: CC-BY-4.0
name: prose-writing
description: House rules for any prose written in this project. Who reads it, which published style guides gate it, and the project's own words. Use when writing or editing a Markdown page, a README, CONTRIBUTING.md, a docstring, a PR title or body, an issue, a review comment, a commit message, or an exception, warning or log message in the code.
---

# Writing prose here

These rules apply to every Markdown page, to the READMEs and [CONTRIBUTING.md](../../../CONTRIBUTING.md), to every docstring in a package's `src/`, to PR titles and bodies, issues, comments and commit messages, and to every exception, warning and log message in a package's `src/` and in `tools/`.
A documentation page also follows [the docs-writing skill](../docs-writing/SKILL.md), which sets the shape of each kind of page.
The form of a PR title is in [CONTRIBUTING.md](../../../CONTRIBUTING.md), under Commits.

This skill does not define a style of its own.
It names the published guides that gate the prose, states which one wins where they differ, and adds the few facts that no guide can know.

**Read [project.md](project.md) in this folder next.**
It contains this project's own rules: its reader, its words, its examples and its extra sections.
Where project.md and this file differ, project.md wins.
This file follows the shared rules of the energy-models copier template, so keep Manta's own rules in project.md.

## The reader

The reader of a page is a user of Manta who knows Python and their own field, and who has read no other page in this repository.
They came to find out what a call returns, and what happens if they write X.
project.md names this reader more closely, and any second reader a page has.

The reader of a PR or an issue is a reviewer who has not seen the conversation.
The reader of a PR title is a changelog reader with no diff.
The reader of a message in the code sees it in a terminal, with their script open and no docs at hand.

Read the text back as that reader before you call it done.
A sentence that does not move their answer forward is cut, however true it is.

## The guides that gate the prose

Check a page against these, in this order.
Where two differ, the earlier one wins.

1. **Google developer documentation style guide**, <https://developers.google.com/style>.
   This is the primary guide for voice, tone, grammar and formatting.
   The parts that matter most here: write in the second person and the present tense; prefer the active voice but use the passive where the actor is unknown or does not matter; use sentence case for headings; do not attribute human qualities to software or to files, which is its rule against anthropomorphism; put conditions before instructions; keep sentences and paragraphs short; use its word list for contested words.
2. **GOV.UK content design guidance**, <https://www.gov.uk/guidance/content-design/writing-for-gov-uk>, and its [A to Z of style](https://www.gov.uk/guidance/style-guide/a-to-z-of-gov-uk-style), for plain English in British spelling: short common words, the fact first, no sentence that needs reading twice, and sentence length judged by the reader and not by a word count.
   Where the Google guide and GOV.UK differ on spelling or punctuation, GOV.UK wins, because the pages are British.
3. **Diátaxis**, <https://diataxis.fr>, for the language of each kind of page: imperatives in a how-to, results after every step in a tutorial, neutral description in reference, argument and comparison in explanation.
   The docs-writing skill contains the per-kind table.
4. **The pandas documentation**, <https://pandas.pydata.org/docs>, as the model of register for a Python library's docs: a concept in a sentence or two, then an example, then a sentence that reads the result.
   Its contributing guide, <https://pandas.pydata.org/docs/development/contributing_documentation.html>, sets the register of a docstring, and the Google style that mkdocstrings parses sets its form.
5. **The US federal plain language guidelines**, <https://www.plainlanguage.gov/guidelines>, where the Google guide is silent: organise for the reader, one idea per paragraph, say it once.

When unsure how to write a sentence, find the construct in the Google guide and follow it.
Do not invent a house rule in its place.

## What this project adds

A handful of facts the guides cannot know.

- **Describe things with flat verbs.**
  A file, an argument, a table, a row, a page or a message does not say, read, hold, carry, own or name.
  It is, has, contains, lists, sets, states, declares, defines, describes or requires.
  The acting verbs, such as reads, writes, builds, refuses, raises and returns, belong to real actors: Manta, a function or method, a tool, or the reader.
  A design decision is Manta's: "Manta refuses a negative timeout", never "the config refuses" or "this project refuses".
  This is the Google guide's rule against anthropomorphism, listed here because pages break it often.
- **Define by category first.**
  "A time series is a table indexed by timestamp."
  Then say what it does.
  A reference entry is a definition, then behaviour, then its arguments.
- **Vary the joiner, and the length.**
  Two sentences that depend on each other may share a sentence through "because", "so", "which" or "when".
  A paragraph in which every sentence does so reads as one voice, and a paragraph of eight-word sentences reads as a list.
  Aim for a page average between 14 and 18 words, with some sentences under 10 and some near 25.
  Treat 25 as the point past which a sentence is read twice, so 25 is in and 26 is out.
  Link text counts as words.
  Judge the sentence by the reader first, as GOV.UK asks, and use the numbers as a check afterwards.
  Where one idea per sentence and the six-sentence paragraph pull against each other, keep the joined sentence.
- **One word, one meaning across the whole set of documents.**
  This is the one rule borrowed from ASD-STE100 Simplified Technical English.
  The word table in project.md applies it to the project's own words.
- **Spelling is British** on pages and in docstrings, and one spelling applies per page.
  Code, keys, identifiers and quoted messages keep their own spelling, so the prose has "normalises" and a method may stay `normalize`.
  No semicolons: write two sentences, a colon or a list.
- **Gloss every acronym and domain term at first use** on a page.
  The explanation, in six words or fewer, runs in the sentence, and the term follows it in parentheses, as the Google guide spells out an acronym before it: "a table indexed by timestamp (a time series)", not "a time series (a table indexed by timestamp)".
  Link the term to the page that defines it, so a term is defined once and linked elsewhere.
- **No history and no promises on a page.**
  "Previously", "renamed from" and "will support" belong in git and the changelog.
- **A number on a page is a measurement.**
  Name what was measured and on what, and put the method in the PR that measured it.

### Project words

The project's own words are in the word table in [project.md](project.md).
Each word in it has the meaning given and no other, and its last column lists the words that drift into the same meaning.
Write the project word instead of those.

## Messages in the code

The reader of a message is the person whose call raised, or who ran a tool.
They see the message in a terminal, with their script open and no docs at hand.
The Google guide's page on error messages applies, and these rules are added:

- **Say what is wrong, where, and what to write instead**, in that order.
  "`timeout` is -1, which no request can wait for. Pass a number of seconds, or `None` to wait without limit." has the argument, the fault and the rewrite, in that order.
- **Name the thing as the caller spelt it.**
  Quote the argument, the key and the value the caller passed, so that they can search their script for it.
  Keep the quoting the module already uses.
- **No "invalid", "illegal", "failed" or "error" on their own.**
  Say which rule the input breaks.
  No exclamation marks.
- **A message after a context prefix**, such as `Column 'price': …`, starts in lower case and continues the sentence the prefix began.
- **Change a message together with what quotes it.**
  A test that matches the text and a page that quotes the message change in the same commit, because the docs quote error messages whole.

## The gate

Before a page, a PR body or an issue is done, read it once against this list.
Each item points at the guide that owns it.
Items 1 to 11 are read on every prose line, item 12 on every sentence, and item 13 on every table.

1. Could a reader who has only the Google guide find a rule this text breaks?
   Fix it.
2. Does any inanimate subject say, read, hold, carry, own or name something?
   Rewrite with a flat verb, or give the sentence a real actor.
3. Does every "that", "this", "it" or "so" point at a noun or verb the text states?
   A pronoun after a negation ("`load` writes nothing. `save` does that") points at nothing.
   Name the thing.
4. Is the subject of each sentence a thing the reader can picture, and is its verb within a few words of it?
   "The value of that argument, which a caller who reads a remote file passes as a string, is a URL or a path" fails twice: the subject is an abstraction, and twelve words sit between it and "is".
   Write "The argument is a URL or a path."
   Use one verb for one action across the paragraph: not drop, prune and discard for the same thing.
   A verb turned into a noun hides the actor the same way: "the application of the filter", "the creation of a cache entry" and "the evaluation of a query" are "when `filter` runs", "when `load` caches the result" and "when a tool evaluates the query".
   A project word in the table in project.md is not a fault.
5. Does each definition say what the thing is before what it is not, with at most one negation, and in nouns the page has already used?
   "A missing value is not a zero, not an empty string and not a default" is three holes and no thing.
   Write "A missing value means no reading exists at that timestamp."
6. When a paragraph moves between situations, such as before and after a call, or one call and a batch of them, does the sentence name the situation first?
   "Before you call `fit`, …", "Once `fit` returns, …".
   An italic phrase is not a marker, and a place such as "in memory" is not a situation.
7. Does every term the reader might not know have a gloss and a link at first use?
8. Does every example end with a sentence that reads the result?
9. Is any sentence over 25 words, link text included, without being a list?
   Is any paragraph over six sentences, or about more than one subject?
   Five rules about five things are five paragraphs, a list, or a table.
   Does the paragraph open with the sentence that states its claim and close with the sentence that states what follows from it?
   A claim that arrives in the middle, or a paragraph that ends on a cross-reference or a detail, is read twice.
   The opening paragraph of a page is exempt, because item 10 sets its first sentence.
10. Does any sentence describe the text instead of the subject?
    "Two cases look alike and are treated differently", "this section covers" and "the point of this is" announce a sentence instead of being one.
    Delete the frame and keep the sentence it announced.
    An opening sentence states what the reader can do after the page, or states the claim the page supports.
    It is never an aphorism such as "a function is what it returns, not how it computes it", and never a question.
    A rule set off in a blockquote is the same aphorism with a frame around it.
    State the rule in a sentence that names the test it applies.
11. Is any claim stated twice on the page, or stated here and owned by another page?
    A paragraph that walks a table's rows or columns in prose is the table said twice.
    Keep the table.
    A clause that restates its own main clause is a sentence said twice: "checks every argument that it can check before the call" is "checks" with its definition hung on the end.
12. Does the point of each sentence sit at its end?
    A reader weights the last words of a sentence, which Gopen and Swan call the stress position.
    "`load` returns an empty frame when the file has no rows" ends on the condition, which the reader already holds.
    "When the file has no rows, `load` returns an empty frame" ends on the point.
    A trailing qualifier, a link back to a known term or an aside after the point is the fault.
    A gloss parenthesis, "(a time series)", is the term's name and not a fault.
    Item 6 is a case of this rule: the situation opens the sentence because the reader holds it.
13. Do the table cells pass items 2, 7, 11 and 12, and the word table in project.md?
    A cell that states a result is a full sentence with its actor: "`load` raises `ValueError` if a column has no header", not "is refused when read".
    A cell that names a thing is a fragment, and every cell in a column takes the same form.
    A cell the body restates in prose is the table said twice: keep one.

The sentence-length script below is an instrument for item 9, not a target.
Put its numbers in the PR's `<details>` when the PR changes prose.

````bash
pixi run python - docs/index.md <<'PY'
import re, sys

SKIP = ('#', '$$', '|', '>', '<', '--8<--', '!!!', '    ')
GENERATED = re.compile(r'<!-- [\w:-]+:(?:begin|end) -->')
ABBREV = re.compile(r'(?:\b[A-Za-z]|\d|\be\.g|\bi\.e|\betc|\bcf|\bFig|\bvs)\.$')


def blocks(path: str) -> list[str]:
    """Prose blocks: one per paragraph and one per list item, code stripped."""
    out, buf, incode, incomment, ingen = [], [], False, False, False
    for line in open(path).read().split('\n'):
        if GENERATED.match(line):
            ingen = line.rstrip().endswith(':begin -->')
            continue
        if ingen:
            continue
        if incomment:
            incomment = '-->' not in line
            continue
        if line.startswith('<!--') and '-->' not in line:
            incomment = True
            continue
        if line.startswith('```'):
            incode = not incode
            continue
        line = re.sub(r'`[^`]*`', 'CODE', line)
        if incode or line.startswith(SKIP):
            continue
        item = re.match(r'\s*(?:[-*+]|\d+\.)\s+(.*)', line)
        if not line.strip() or item:
            if buf:
                out.append(' '.join(buf))
            buf = [item.group(1)] if item else []
            continue
        buf.append(line.strip())
    if buf:
        out.append(' '.join(buf))
    return [b for b in out if b.strip()]


def sentences(block: str) -> list[str]:
    """Split on terminal punctuation, rejoining across `1.5`, `e.g.` and initials."""
    parts, cur = [], ''
    for chunk in re.split(r'(?<=[.!?])\s+', block):
        cur = f'{cur} {chunk}'.strip()
        if not ABBREV.search(cur):
            parts.append(cur)
            cur = ''
    if cur:
        parts.append(cur)
    return [p for p in parts if p.strip()]


w = sorted(len(s.split()) for b in blocks(sys.argv[1]) for s in sentences(b))
print('n', len(w), 'avg', round(sum(w) / len(w), 1), 'median', w[len(w) // 2], 'over25', sum(x > 25 for x in w))
PY
````
