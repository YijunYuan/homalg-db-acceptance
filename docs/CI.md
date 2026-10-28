# CI and repository governance

The workflows separate inexpensive metadata and collaboration checks from Lean
builds. GitHub settings are applied separately using the governance command below.

## Checks and deployment

`validate.yml` produces the required `gate` check from four jobs:

- `classify` inspects the changed paths and fetches live PR labels. Claim and
  registration PRs skip Lean; fixture changes count as infrastructure. Progress
  branches under `status/` cannot be merged.
- `checks` validates metadata, applies current-main claim ownership and expiry,
  counts pending claim PRs, enforces document scope and append-only taxonomy, and
  blocks ordinary PRs while the latest main deployment is red. `repair` opts into
  repairing main. Infrastructure changes also run tests and build the site.
- `lean` builds the selected document, or the entire library for infrastructure,
  regenerates Lean metadata, validates it, and rejects uncommitted generated-data
  changes. It posts a review summary for document PRs.
- `gate` requires successful classification and checks, and successful or
  deliberately skipped Lean work. Failure and cancellation cannot pass.

`owner-approval.yml` independently checks sensitive document fields, multiple
changed documents, taxonomy-maintenance changes and proof-route dispute
resolutions. The owner's latest decisive review must approve the exact current
head SHA; the owner's own PRs pass. Review submission/dismissal reruns this check
without rebuilding Lean. A merge group relies on its constituent PR approvals.
The workflow invokes `homalg pr-check --owner-only`, using the same policy API
that the main validator can call through its PR options.

`deploy.yml` validates and builds full data on pushes to `main`, daily at 03:17 UTC,
and by manual dispatch. It saves only `.lake/build` immediately after Lean's build,
checks generated-data freshness and size budgets, then deploys `site/dist` through
`github-pages`. The Vite build uses the repository's Pages path (`/REPO/`, or `/`
for an account site), so JavaScript, styles and data resolve beneath the deployed
project URL. A failed build leaves the previous site online. Deployments are
serialized without cancelling an earlier deployment. `release-data.yml` builds
a weekly validated snapshot and attaches the data, LICENSE, LICENSE-DATA and
NOTICE to a dated GitHub Release.

Every workflow denies permissions by default and grants only the job permissions
it needs. Explicit Bash enables `pipefail`; a failed `lake build | tee` fails CI.
All referenced actions are pinned to upstream commit SHAs. There is no
`pull_request_target` workflow. The selected upstream tags are documented inline:
[checkout](https://github.com/actions/checkout),
[setup-uv](https://github.com/astral-sh/setup-uv),
[setup-node](https://github.com/actions/setup-node),
[lean-action](https://github.com/leanprover/lean-action),
[upload-pages-artifact](https://github.com/actions/upload-pages-artifact), and
[deploy-pages](https://github.com/actions/deploy-pages).

## Prepare and apply governance

Use an existing GitHub repository with the default branch `main` and an account
with repository administration permissions. The script never creates repositories
or opens pull requests. The checked-in `CODEOWNERS` initially contains comments
only because the repository owner's login is not yet configured.

Preview the complete plan without contacting GitHub or changing files:

```sh
make governance GOVERNANCE_ARGS='--repository OWNER/homalg-db'
```

Render actual ownership locally, inspect the diff, and commit/push it with the
workflows before enabling the rulesets:

```sh
python3 tools/scripts/governance.py --repository OWNER/homalg-db --write-codeowners
```

Apply an already-reviewed plan explicitly:

```sh
make governance GOVERNANCE_ARGS='--repository OWNER/homalg-db --apply'
```

`HOMALG_REPOSITORY=OWNER/homalg-db` can replace `--repository`.
`GOVERNANCE_OWNER_KIND=user` is the default. Organization mode requires
`--owner-kind org --owner-login MAINTAINER --team-id ID`; it verifies that the ID
belongs to `OWNER/homalg-maintainers` before writing. `HOMALG_OWNER` is always the
human maintainer's login, while CODEOWNERS uses the organization team.

The idempotent script creates or updates `main` and `status-branches` rulesets,
reads them back to verify their contents, enables squash-only auto-merge and
branch deletion after merge, restricts default workflow permissions to read,
sets Pages Source to GitHub Actions, sets `HOMALG_OWNER`, and creates or updates
the twelve specified labels. Existing resources are updated by identity. Network
failure can leave a partially applied plan; review the failure and rerun to finish.

The two required checks are `gate` and `owner-approval`. CODEOWNERS protects
infrastructure, schemas, the site, and relation review decisions while exempting
node paths, document metadata, and append-only taxonomy/relationship paths.
Those exemptions are checked by the metadata and collaboration policy commands. Personal repositories permit the repository administrator to
bypass in pull requests, as required to avoid blocking the sole owner's own PRs.
Add a second maintainer for meaningful independent code-owner review.

A registration-only document has no Lean node imports yet. Compiled existence
checks for its foundation names are deferred and explicitly reported as
`mathlib-decls-exist:DOC:no-node-modules` in skipped coverage. The first node
restores strict compiled lookup checks; a misspelt or unavailable foundation then
fails validation. Metadata schema and review-provenance checks remain active
during registration.

Remote acceptance must be exercised in a test repository: a contributor's
infrastructure PR must require owner review, an eligible formalization PR must
pass without it, and a claim PR must auto-merge after both required checks pass.
The local tests exercise these rules with temporary Git repositories and fake GitHub responses; they do not certify live repository settings.

## Local pre-commit hook

Install with `git config core.hooksPath .githooks`. The hook rejects staged PDF
paths, runs Ruff and fast metadata validation, and checks site formatting with the
locked Prettier dependency. M0 checks the whole repository with `--fast`; the
planned `--changed` filter will be added in M1 once Git base selection is available. Horizon ledger commits use a separate Git directory
and do not pass through this hook.

## Cache and runner policy

The workflows cache only the project's `.lake/build`, keyed by the toolchain and Lake
manifest. Mathlib cache downloads and `~/.elan` stay outside the GitHub cache.
Consider a self-hosted runner when a cold build exceeds three hours, routine
incremental PR builds exceed 45 minutes, a compressed cache exceeds 4 GB, a module
needs over 16 GB memory, or the library reaches roughly 8,000 modules. Set the
repository variable `LEAN_RUNNER=lean-large`; the Lean job honors
this runner override.
