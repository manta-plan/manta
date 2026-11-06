---
# SPDX-FileCopyrightText: Manta contributors
# SPDX-License-Identifier: CC-BY-4.0
name: docs-writing
description: House rules for documentation pages in this project, built on Diátaxis. What kind of page to write, where it lives, how each kind is written, and how its examples, figures and headings work. Use when writing, restructuring or reviewing a documentation page or section, or when adding prose to an existing one, together with the prose-writing skill.
---

# Writing docs here

These are the rules a page has to meet.
They apply to prose you write now and to prose already on the page: a page that does not meet them is not finished, whoever wrote it.

**Load [the prose-writing skill](../prose-writing/SKILL.md) first.**
It sets the reader, the voice, the sentences and the words, for pages, PRs and issues alike.
This skill adds what only a page needs.

**Read [project.md](project.md) in this folder next.**
It contains this project's own rules: what each nav section holds, the running example, what each figure colour means, and its generated content.
Where project.md and this file differ, project.md wins.
This file follows the shared rules of the energy-models copier template, so keep Manta's own rules in project.md.

The docs follow [Diátaxis](https://diataxis.fr), which sorts documentation by the need of the reader into four kinds: tutorials, how-to guides, reference and explanation.
Diátaxis is an approach, not four boxes to fill.
This skill is how Manta applies it, and each section links the Diátaxis page it draws on.
Turn to that page when a rule here does not settle a question.

## 1. Decide what the page is before writing a sentence

Two questions decide it, and they work on a paragraph as well as a page ([the compass](https://diataxis.fr/compass/)):

1. Does it inform **action** or **cognition**?
2. Does it serve **acquiring** a skill or **applying** one?

| Kind        | Informs   | Serves  | Answers                                          | Section · folder              |
| ----------- | --------- | ------- | ------------------------------------------------ | ----------------------------- |
| Tutorial    | action    | acquire | "Teach me to use this, from nothing"             | Tutorials · `docs/tutorials/` |
| How-to      | action    | apply   | "I have this task"                               | How-to guides · `docs/howto/` |
| Reference   | cognition | apply   | "What exactly does X accept, return and refuse?" | Reference · `docs/reference/` |
| Explanation | cognition | acquire | "Why is it like this?"                           | Explanation · `docs/explanation/` |

Ask the two questions again whenever writing feels hard or a paragraph will not settle.
That doubt is the sign of text that serves two needs at once.

Each kind has one job, and one thing it must not do:

- **A tutorial is a lesson.**
  One path, every step shows a result, and the reader finishes with something that works.
  It explains nothing and offers no choice: a choice is a how-to leaking in.
  Where a step needs a reason, one clause and a link to the explanation page give it.
  The last section, before "Where to next", states what the reader has built.
- **A how-to is a recipe.**
  The title names the goal, the body is the steps, and the reader is assumed competent.
  It neither teaches nor explains: a term is linked to the reference, never defined.
  A rule is linked, never restated.
  A consequence is one sentence, never a section.
- **Reference describes, and only describes.**
  One consistent format, and a structure that mirrors the code it describes.
  No rationale, no instruction.
  An example illustrates an entry and never turns into a recipe.
  A recipe is a link to the how-to.
- **Explanation is the one place for why.**
  Context, alternatives and opinion live here and nowhere else.
  An explanation page names the alternative it rejects and states why the choice is better here.
  It contains no table of arguments, no checklist and no instruction.
  It links the reference or the how-to for those.

**The Python API is rendered from the docstrings.**
`docs/reference/playbook/api.md` contains `:::` entries for `playbook.blocks` and `playbook.playbooks`, and `docs/reference/runner/api.md` one for `runner`.
mkdocstrings renders them from Google-style docstrings, and their prose follows the prose-writing skill.
No other module gets a page: an internal module is read in the source.
The REST API page is generated from the backend's OpenAPI schema (see project.md).

### Tutorial or how-to

Both are steps, so they are the pair most often confused ([tutorials and how-to guides](https://diataxis.fr/tutorials-how-to/)).
Ask whether the reader is at study or at work, not whether the subject is basic or advanced.
A how-to can cover a basic task, and a tutorial can teach an advanced one.

| A tutorial                              | A how-to                                                |
| --------------------------------------- | ------------------------------------------------------- |
| follows one path you set up in advance  | meets the reader's real project, which you cannot see   |
| removes the unexpected                  | states what to do when the unexpected happens           |
| offers no choices                       | forks: "if you need x, do y"                            |
| is safe to run again from the start     | may change something that cannot be undone, and says so |
| states what to type and what to run     | assumes the reader knows the basics                     |
| uses one concrete case, with known data | states a general approach that fits many cases          |

### Reference or explanation

Ask whether the reader would turn to the text while working, with the code open ([reference and explanation](https://diataxis.fr/reference-explanation/)).
If so, it is reference.
If they would read it after stepping away from the work, to think, it is explanation.
A list of classes, arguments or options, or a table of facts, is reference.
The answer to "can you tell me more about X?" is explanation.
Text beside a reference example about why it behaves so, or how it came to be, is explanation.
It moves to an explanation page.

### Mixing kinds

Mixing kinds is the most common failure ([the map](https://diataxis.fr/map/)).
Rationale inside a reference section makes the facts hard to skim, and rules inside an explanation page break the argument.
Rationale about the code, its internals and its measured numbers belongs in the PR.
Rationale about the design, the alternatives it rejects and what it costs belongs on an explanation page, where a user can read it before relying on a rule.

Each kind has its own sentence patterns, from [Diátaxis](https://diataxis.fr):

| Kind        | Opens with                                                                            | Sentences                                                                                                                                        | Closes with                              |
| ----------- | ------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------ | ---------------------------------------- |
| Tutorial    | "In this tutorial you build …", and how long it takes                                 | "Run this … Check it:", then the output, then one sentence that reads it. "If the output shows x, then …"                                        | "You have built …", then "Where to next" |
| How-to      | "This guide shows how to …", and what you need before                                 | "To get x, do y." "If you want w, pass z." "The [reference](…) lists every argument."                                                            | The result, checked                      |
| Reference   | What the thing is, in one sentence, then its shape                                    | Facts. "`load` accepts …", "`load` raises …", "`load` refuses …". Never "to get x, do y".                                                        | a "See also" admonition                  |
| Explanation | The decision, as one statement, or what the page covers, when it has several (see §4) | "Here x is better than y. The reason is …", "x is like w in z", "the rule exists because …", "what you write instead" with the reader as subject | What the reader can now judge            |

Manta is documented here and only here.
A page states what a call accepts, returns or refuses, and what Manta writes.
What another framework does with the result is that framework's documentation, and a page names the framework only for what Manta reads from it or hands to it.

Answer the two questions before starting.
If a page needs two kinds, it is two sections with two headings, or two pages that link each other.

## 2. Where a page lives

The folder, the kind and the nav section are one thing.
A new page goes in the folder of its kind and under the nav section of the same name.
Each section opens with an `index.md` that lists its pages, and a new page adds its line there.
project.md states what each section holds in this project.

**Do not create empty structure** ([how to use Diátaxis](https://diataxis.fr/how-to-use-diataxis/)).
A folder, its `index.md` and its nav section appear with the first page of that kind, and not before.
A section named "Tutorials" with nothing under it tells the reader the docs are unfinished.

**A landing page reads as an overview, not a list** ([complex hierarchies](https://github.com/evildmp/diataxis-documentation-framework/blob/0c9022ecbd82f8cd42069886faae40cd91eb8995/complex-hierarchies.rst)).
It opens with a sentence or two on what the section offers, then links each page with one line that states why a reader would open it.
Keep each list to about seven items, unless it has a mechanical order such as alphabetical.
Split a longer list into groups, each under a short heading with a sentence that introduces it.
When a section grows past that, give a group a subfolder with its own `index.md`, one level deeper.

**Document Manta as the user holds it, not as the code is organised.**
A structure built around the modules of the code rarely helps a reader find a task or a lesson.
Reference is the exception, because it mirrors the code on purpose (see [Reference](#reference)).

**More than one audience gets its own arrangement.**
Pages for someone who changes Manta, such as the contributing guide, belong in the Contributing section, last in the nav.
Pages for someone who builds a tool on top of Manta can follow the user pages in the same way.
Each page still keeps the folder and the shape of its kind, and no page mixes two kinds to serve two audiences.

A reader may enter the docs on any page, from a search engine or a link.
So every page names what it needs the reader to know already, and links the page that teaches it.

## 3. Writing each kind

### Tutorials

A tutorial is a lesson, and you are responsible for the reader's success ([tutorials](https://diataxis.fr/tutorials/)).
You cannot be there when they get stuck, so the page does the work a teacher would.

- Give the reader things to do, not things to read.
  They learn by doing the steps, not from your explanations.
- Show the destination first: "In this tutorial you build a cleaned table of meter readings."
  Not "In this tutorial you will learn …", which promises what only the reader can do.
- Give each step as a plain instruction: "Install the package. Open a Python session."
- Show a visible result early, and after every step.
  A step that joins a purpose, an action and its result gives the reader a rhythm, and the confidence to take the next one.
- Show the exact expected output, and state what a wrong result looks like: "If the output shows `KeyError: 'date'`, the file was read without its header row."
- Point out what to notice: "The index is now the date column."
  Warn before a step that prints a lot or takes a while.
- Make every step safe to repeat, so the reader can go back and run it again.
- Cut explanation to one clause, and link the explanation page for the rest: "Pass `parse_dates`, so that pandas reads the column as dates."
- Stay concrete: this data, this call, this result.
  General patterns come later, from the reader's own work.
- Leave out options and alternatives.
  Each one is a how-to or a reference entry, and the tutorial links it.
- Plan what the reader does apart from what they learn by doing it.
  Then check that every step has a purpose the reader can see and works when followed exactly.
  Check too that the steps cover every action the reader needs to finish.
- Run the whole tutorial from a clean environment before every change to it.
  A change to Manta can break every step after it, so a tutorial costs the most to maintain of the four kinds.
  Watch a newcomer follow the page to find the flaws that remain.

### How-to guides

A how-to directs a competent reader through a real task ([how-to guides](https://diataxis.fr/how-to-guides/)).
The list of guides on the section's landing page also shows a reader what Manta can do.

- The title and every `##` are imperatives that name the task (see §7): "Read data from a remote bucket", not "Remote data".
- Open with the task, "This guide shows how to …", and name what the reader needs before they start.
- Write from the user's goal, not from the code: "Resume an interrupted download", not "Use `RetryPolicy`".
  A guide may use several functions, or several tools, where the task needs them.
- Write action, and only action.
  Link the explanation page where the reader may want the reason, and link the reference for the full list of options.
- Spend the words on what the reader cannot guess: which option fits which situation.
- Use conditional imperatives where the task forks: "If the bucket is public, pass `anon=True`."
  A step may be a decision rather than a call, so state what the reader weighs to make it.
- State what to do when a step fails in a way the reader is likely to meet.
- Start and end at a useful point.
  Leave out what the reader already has set up, and stop when the task is done.
- Order the steps so that each one sets up the next.
  A reader who holds a thought open for several steps before they can act on it loses it.

### Reference

Reference describes Manta, so that a reader at work can look up a fact and trust it ([reference](https://diataxis.fr/reference/)).

- Describe, and only describe: neutral, factual and austere.
  Link the how-to or the explanation page for instruction and rationale.
- Mirror the structure of the code: one page per module, class or group of options, in the order the code has them.
  A reader who knows the code then knows where to look, and a missing entry shows as a gap.
- Give every entry of the same type one format, so the reader learns it once.
  Put each fact where a reader of other Python libraries looks for it.
- List every argument, option, default, limitation and exception that a caller can meet.
- Give each entry a short example that shows a call and what it returns.
- State requirements and prohibitions flatly: "must", "must not", "never", "unless".

A hand-written entry has the three parts in §10.
The rendered API is not the whole of the docs: a reader still needs the other three kinds to use Manta.

### Explanation

Explanation helps the reader understand Manta, away from the task at hand ([explanation](https://diataxis.fr/explanation/)).
It is less urgent than the other kinds, and no less important.
Give it the Explanation section, rather than scattering it across tutorials and reference.

- Title it so that "About" fits in front: "Caching and invalidation", read as "About caching and invalidation".
  A real or imagined "why" question sets its scope.
- Give the context: the design decision, the technical constraint, or the history behind the code as it is.
  Then draw out what follows from it, with a concrete example.
- Connect it to other parts of Manta and to ideas outside it, where that helps the reader see the whole.
- Weigh the alternatives, state which one Manta chose and why, and name the cases where another library's choice is better.
- Keep it bounded: steps go to a how-to and technical description to the reference, and the explanation links them.

## 4. Open with what the reader can do

The first sentence, above the first rule, states what the reader can do once they have read the page.
Do not restate the title.
A page with one point opens with that point, as a definition or a decision: "A time series is a table indexed by timestamp".
A page with several points, which no one sentence covers, opens with what it covers instead, as the pandas documentation does ("This page describes every argument `load` accepts").
The strain is the test: a one-sentence claim that needs a metaphor, a second clause or a word the body has not defined yet is the sign of several points.
Never open with a question or an aphorism.
A coverage sentence is allowed at the top of a page and nowhere else: "in this section we will" and "this page contains" further down are frames.

The prose is the prose of the pandas documentation: a concept in a sentence or two, then the example, then one sentence that reads the result.
An example is never left for the reader to interpret.
A section that has a sibling elsewhere ends with a `!!! info "See also"` admonition that links it.
An aside that would break the flow of a section goes in a `!!! note` or `!!! warning` admonition, at most two per section.

Then the shape a reader needs, in this order:

1. **Shape**: the smallest call that works.
2. **Rules**: what is accepted, and what is refused.
3. **Rationale**: only where it changes what they write.

The subtlest rule gets the most support: a list, a worked example, a table.
The obvious rule gets one sentence.

## 5. Every rule has an example, and the example is real

- **Show the input and its result side by side.**
  A call next to the frame it returns.
  Never in a later subsection.
- **Run every Python example before committing it.**
  No test reads a fence on a page, so a fence is only as true as its last run.
  Run it with `uv run python` in the package's folder (`pixi run python` in `playbook-library/`) against your branch, and paste the real output.
  A fence that cannot run alone, such as one line of a longer session, follows the fence that sets up its names on the same page.
- **Use the running example** that project.md names, where it has one.
- **Quote error messages whole.**
  A truncated quote drops the half that states what to write instead.
- **Prefer the smallest example that still shows the point.**
  A frame with two columns and three rows teaches.
  A realistic one hides the rule in scenery.
- **Show the refused form too**, where the refusal is the lesson, with the message it raises.

## 6. A rule about rows has a figure

A section of a reference or explanation page that states what a function does to the rows of a table has a figure.
A figure about structure or flow may use labelled boxes and arrows instead of tables.
A tutorial or a how-to links to the figure and draws none of its own.

- **Every table is drawn as a table, one row per row of the data.**
  Where no row exists, the table has none, and a dashed rounded box with an italic note stands where the row would be: "no row: `coal` is dropped".
- **A second key is a second column.**
  Use one only where it changes the result.
  A figure has at most two result panels to the right of its input, and more go on a row below.
- **The figure uses the data of the section's example.**
  Where the page has no data, invent the smallest set and say so in the PR.
- **Code appears once.**
  A figure that follows a fence contains no code.
  A figure with no fence above it opens with the few keys or the call it is about, and the key in question is in bold.
- **One mark, one meaning, on every page.**
  The colours are the Okabe-Ito palette: blue `#0072B2`, orange `#E69F00`, bluish green `#009E73`, vermilion `#D55E00`, reddish purple `#CC79A7`, sky blue `#56B4E9` and yellow `#F0E442`.
  project.md assigns each colour its meaning.
  A vermilion hatch is a row that a step drops, and a dashed outline with no fill stands where no row exists.
  The hatch never highlights.
  A tint fills a table's header band at `fill-opacity="0.2"` and its body at `0.08`, under the text.
  Text, outlines and arrows stay `currentColor`, so the figure reads in light and dark mode.
- **No rule is stated in colour alone.**
  Each coloured table has a text label for its kind, and a legend lists the marks the figure uses, and no others.
- **An arrow meets its target at a right angle.**
  Draw it as a curve that ends in a short straight run, or as an elbow.
  A fan from one table to several is an elbow tree.
  The arrow has a short label: the call, then what it does.
- **The words are the page's words**, from the word table in the prose-writing skill's project.md.
- **The file** is `docs/static/<page>-<topic>.svg`.
  It opens with the SPDX header as an XML comment, then `<svg>` with `width`, `height`, `style="max-width: 100%; height: auto"`, `role="img"`, and a `<title>` and `<desc>` that `aria-labelledby` lists.
  Every `id` takes a prefix of the figure's own, because one page shows several figures.
  Colours are attributes, because a `<style>` element in an inline SVG styles the whole page.
  The file has no blank line, because a blank line ends the raw HTML block.
- **Embed it inline**, after the fence and before the sentence that reads the result, so `currentColor` follows the theme:

  ```markdown
  <figure class="diagram">
  --8<-- "docs/static/<page>-<topic>.svg"
  </figure>
  ```

- **Look at it in both themes** before the page is done.
  No environment of this project contains `rsvg-convert`, so `pixi exec` fetches it:

  ```bash
  pixi exec --spec librsvg rsvg-convert -w 1520 -b white x.svg -o light.png
  sed 's/currentColor/#ddd/g' x.svg | pixi exec --spec librsvg rsvg-convert -w 1520 -b '#1e2129' -o dark.png
  ```

  Text over the strongest tint keeps a contrast of 4.5:1 in both.

## 7. Headings are the table of contents

- **A heading takes the form of its kind.**
  On a how-to page, the title and every `##` are imperatives that name the task: "Read data from a remote bucket", "Choose between a cache and a fresh read".
  Not a gerund ("Reading remote data") and not a noun ("Remote data"), which Diátaxis grades bad and very bad, because a reader searches for the task.
  On a tutorial page, a `##` names what the step adds: "The input file", "A cleaned table".
  On a reference page, a heading names the construct, in the order its source has it: "`load`", "`timeout`".
  On an explanation page, a heading names the subject or the question: "Caching and invalidation", "Why `load` copies its input".
- **Elsewhere a heading names the subject, or the question the section answers.**
  "Missing values", "How a reader is registered".
  The test: a reader who types the subject into the search box lands on this heading.
- **A heading never states a conclusion.**
  A heading is read before the section, so it cannot depend on it.
  "Unknown keys", not "An unknown key is refused".
  Put the claim in the first sentence, where the reader can act on it.
- **No second clause after a comma or a dash.**
  "Two states, and the difference between them" is a heading and an aside.
  Keep the heading, or make two sections.
- **One `##` per idea.**
  A section that needs a paragraph of preamble before its first rule is two sections.

## 8. Bold is for terms and permissions

On a page, bold marks a term where the page defines it, and a short phrase that changes what a sentence permits.
A page has no bold lead-in on its list items, and bold is never a whole sentence.
Where a list must skim, make the first sentence of each item the claim:

```markdown
- Missing values spread through arithmetic. A sum with one missing term is missing.
```

not

```markdown
- **Arithmetic.** ...
```

## 9. Vocabulary

The prose-writing skill's project.md contains the word table.
On a page, two more rules apply:

- **Gloss where the term is used**, explanation in the sentence and the term in parentheses, and link the reference page that defines it rather than redefine it.
  A second definition drifts.
- **Link the reference at a construct's first mention** on the page.
  A function or a class links to its entry in `docs/reference/<package>/api.md`.

## 10. A reference entry

An entry in `docs/reference/` has three parts, in this order.

1. **What it does to the data, verb first, arguments in plain words.**
   "Shifts array elements by a given offset along a single dimension."
   Not a metaphor ("reaches along an axis"), and not notation the reader must bind to the signature themselves (_t−n_).
2. **What it does not do.**
   "Only data is moved, and coordinates stay in place."
   The sentence that stops a wrong assumption is worth more than any other in the entry, and it is the one most often missing.
3. **What each remaining argument is for**, at that level.
   "An additional `fill_value=` argument sets the value of positions shifted in from beyond the array bounds."
   The list of its values follows, or lives in the section that defines it.

## 11. What does not go on the page

- **History.**
  "Previously this used to …" and "renamed from …" are git's and the changelog's.
  History that explains why the design is the way it is belongs on an explanation page.
- **Argument on a tutorial, how-to or reference page.**
  The argument for a design rule goes on an explanation page.
  The argument for a change to the code goes in the PR.
- **A promise about the future.**
  "Will support …" ages into a lie.
- **Anything that duplicates another page.**
  One fact has one home, and other pages link it.
  A second copy drifts silently.
  `docs/index.md`, the installation pages and the contributing pages pull in parts of `README.md`, `CONTRIBUTING.md` and the package READMEs as snippets, so a sentence that appears in both places is edited once, at its source.
- **Another framework's rules.**
  How another framework uses what Manta returns is that framework's documentation.
- **Generated content, edited by hand.**
  The `api.md` pages under `docs/reference/` are `:::` entries that mkdocstrings renders.
  Change the docstring, then read the rendered page.
  project.md lists any other generated block and the tool that writes it.

## 12. Mechanics

- **The build is Zensical, from `mkdocs.yml`, and it is strict.**
  A dead cross-link or a missing anchor fails `pixi run docs-build`.
- **A new page needs a nav entry in `mkdocs.yml`** and a line in its section's `index.md`.
  Nothing checks the nav: a page with no nav entry still builds, so check it by hand.
- **A new page has the SPDX header**, `Manta contributors` and `CC-BY-4.0`, in an HTML comment at the top.
  Nothing checks it yet.
- **Inside `docs/`, link relatively.**
  Outside it, write the full GitHub URL, `https://github.com/manta-plan/manta/blob/main/<path>`.
  A relative link above `docs/` renders in the repository and fails the strict build.
  Text pulled in from a README or `CONTRIBUTING.md` is rendered under `docs/`, so its links to files outside `docs/` are full URLs too.
- **A snippet is `--8<-- "path"`**, with the path from the repository root.
  `--8<-- "README.md:docs-preamble"` takes the part between the `[start:docs-preamble]` and `[end:docs-preamble]` markers.
- **A list item with a second paragraph or a fence needs four spaces and a `<!-- prettier-ignore -->` line above the list.**
  Python-Markdown needs four spaces for the continuation, and prettier rewrites them to two, so without the ignore line the content renders outside the list.
  Nothing checks this.
  Prefer one paragraph per item and put the fence after the list.
- **Write no release number on a page.**
- **Tables for what varies along one axis**, such as the arguments of a function or the columns of a file.
  Prose for what has an order or a reason.

## 13. Work one step at a time

Improve the docs in small steps, and do not plan a rewrite of the whole tree ([how to use Diátaxis](https://diataxis.fr/how-to-use-diataxis/)).
A good structure grows from good pages, and nobody can impose it on them from above.

1. **Choose** a piece of the docs: the page in front of you, or the one your change touches.
2. **Assess** a paragraph or a sentence of it, not the whole page.
   Ask what need of the reader it serves, and whether its language fits that kind.
3. **Decide** on the one next action that improves it now: move a paragraph to its kind's page, cut a digression, or add the missing example.
4. **Do** it, and let the step stand on its own in its commit.

Then choose again.
After every step the docs are complete: useful now, sound in structure, and ready for the next step.

## 14. Quality

A page has two kinds of quality, and the second depends on the first ([quality](https://diataxis.fr/quality/)).

**Functional quality** is checked: the page is accurate, complete, consistent, precise and useful.
Each is a separate property, so a page can be accurate and still incomplete.
The gates in §16 check some of it, and you check the rest against the code as it is now.
Sorting text by kind exposes gaps: a reference page that mirrors the code shows a missing entry, and explanation lifted out of a tutorial shows the step the reader was left to work out alone.

**Deep quality** is judged, not measured: the page fits the reader's need, it flows, and it anticipates the next question.
Keeping the kinds apart makes that possible, because nothing interrupts the reader's work or study.
Read the page as its reader, at study or at work, and fix what makes them stop.

## 15. The structure gate

Before any sentence is checked, read the heading tree alone and answer these five questions.
Structure is fixed first, because moving a section moves its sentences.

1. Does each section sit under the heading that names its subject?
   A section about refused arguments under "Reading a file" is misfiled.
2. Does the argument for a thing sit beside the thing?
   An explanation page weighs the alternative where it introduces the subject, not three paragraphs later.
3. Is every section the page's own kind?
   A table of `load`'s arguments inside an explanation page is reference, and belongs on the reference page it duplicates, with a link here.
4. Does a topic appear in one place?
   Two tables that state the same thing, or a section wedged between the two halves of another, are one topic split.
5. Does the page close as its kind closes?
   An explanation page ends with what the reader can now judge, a tutorial with what they built, a reference page with a "See also" admonition, and a how-to with the result checked.

## 16. Gates

```bash
pixi run docs-build   # strict: a dead link or a missing anchor fails
```

CI runs the same build on every pull request that touches the docs or the code they render.
Run every Python example you changed as §5 states, and look at every figure you changed in both themes (§6).
project.md lists any further gate.
Say which gate ran and what was left unrun.
