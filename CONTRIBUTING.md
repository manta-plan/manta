# Contributing to Manta

Manta is a monorepo containing a Python backend (`backend/`) and, a
Javascript frontend (`frontend/`). This document is the canonical reference for coding
standards on the project. It applies to everyone pushing code — core team,
energy modelers, and outside contributors alike.

If a file or module doesn't clearly fit the conventions below, raise it in your
PR rather than guessing — conventions get updated by discussion, not by silent
drift.

## General

### Commits

We squash-merge PRs, so the **PR title** becomes the commit message — that's
what needs to follow a convention, not individual commits. We use a reduced
version of [Conventional Commits](https://www.conventionalcommits.org/), since
the full spec assumes one type per commit, which doesn't hold once a PR's
commits get squashed together:

```
<type>[!]: <imperative description>
```

- `type` is one of `feat`, `fix`, or `docs` — use `docs` only when the PR is
  docs-only; a feature PR that happens to touch docs too is still `feat`.
- No scope (e.g. no `(backend)`) — it's not worth the overhead.
- Append `!` for breaking changes (e.g. `feat!:`), enough on its own to drive
  a changelog.
- The description should be imperative and descriptive — read it as
  completing "If applied, this commit will...".

- Open a PR against `main` for review before merging.
- Style/formatting disputes are considered solved problems — defer to the
  linter/formatter for the language you're working in rather than debating it
  in review.

## Backend (Python)

The backend follows a **Model-Service-Controller (MSC)** pattern — essentially
MVCS adapted for a JSON API, where the "view" is folded into the controller
since we return data, not rendered pages. Background on the classic pattern:
[MVCS introduction](https://pvha.hashnode.dev/mvcs-architecture);
for how this maps onto FastAPI specifically, see
[FastAPI's bigger-applications guide](https://fastapi.tiangolo.com/tutorial/bigger-applications/).

| Layer               | Responsibility                                                                 |
|---------------------|---------------------------------------------------------------------------------|
| Route (Controller)  | Accept input (via a `Request` class), call a service, shape the output. **No business logic.** |
| Service             | All business logic. Implemented as a class, returns dedicated `Result` objects rather than raw data. |
| Entity (Model)      | Business entities, kept separate from both of the above. Called `entities/` in code, not `models/`, to avoid clashing with energy *models* (PyPSA etc.) elsewhere in the domain. |

Cross-cutting concerns (auth, CORS, etc.) live in `middleware/`, not in services.

### Directory structure

Files are grouped by type (not feature) for discoverability.

```
backend/
├── pyproject.toml
├── uv.lock
├── alembic.ini                 # alembic CLI config — see backend/README.md
├── src/
│   └── manta/
│       ├── main.py            # app entrypoint
│       ├── routes/            # *_route.py, grouped by API version (v1/, v2/, ...)
│       │   └── v1/
│       │       └── requests/  # *_request.py — input DTOs, versioned with their routes
│       ├── services/          # *_service.py — version-agnostic business logic
│       │   └── results/       # *_result.py — output DTOs, shared across versions
│       ├── entities/          # business entities
│       ├── migrations/        # alembic env + versions — see backend/README.md
│       ├── config/            # app config (logging, database, ...)
│       └── middleware/        # cross-cutting concerns (auth, CORS, ...)
└── tests/                     # pytest suite — see Testing below
```

### Naming

Use explicit suffixes so a filename alone tells you the layer: `user_route.py`,
`user_service.py`... Same for class names: `GetUserResult`, `UserService`, `AuthMiddleware`... 
Entities are named after themselves (e.g. `user.py` / `User`), no suffix needed.

### Services & dependency injection

Services are always classes, wired up via
[FastAPI's dependency injection](https://fastapi.tiangolo.com/tutorial/dependencies/)
rather than instantiated ad hoc — this gives consistent, predictable
initialization instead of hand-rolled setup.

### Linting & formatting

Python code is linted and formatted with [Ruff](https://docs.astral.sh/ruff/),
configured in `backend/pyproject.toml`.

- **Locally**, a [pre-commit](https://pre-commit.com/) hook runs Ruff against
  `backend/` and auto-fixes what it can before each commit — see
  [backend/README.md](backend/README.md) for one-time setup.
- **In CI**, the same Ruff checks run read-only on every PR: they fail the
  build on violations but never push a fixup commit. If pre-commit was
  skipped or bypassed, fix locally and re-push.

### Testing

We use [pytest](https://docs.pytest.org/). `backend/tests/` is split by test
type, mirroring `src/manta/` inside each:

```
backend/tests/
├── unit/           # e.g. tests/unit/services/
└── integration/    # e.g. tests/integration/routes/
```

Structure test bodies as **Given/When/Then**, using plain comments.

**TODO**: expand this with more guidance (fixtures, mocking conventions, what
belongs in unit vs. integration) as we accumulate more tests to draw examples
from.

## Frontend

TBD
