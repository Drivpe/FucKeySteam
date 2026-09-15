# Issue tracker: GitHub

Issues and specs for this repo live in [Drivpe/keysteam-unlock-spike](https://github.com/Drivpe/keysteam-unlock-spike) (private). Use the `gh` CLI for all operations.

## Conventions

- **Create an issue**: `gh issue create --title "..." --body "..."`. Use a heredoc for multi-line bodies.
- **Read an issue**: use the REST API, **not** `gh issue view`:

  ```
  gh api repos/Drivpe/keysteam-unlock-spike/issues/<n> --jq '{number,title,state,labels:[.labels[].name],body}'
  gh api repos/Drivpe/keysteam-unlock-spike/issues/<n>/comments --jq '.[] | {id,created_at,author:.user.login,body}'
  ```

  **Why not `gh issue view <n> --comments`**: on this machine (gh 2.46.0) that command fails outright — the GraphQL query requests `repository.issue.projectCards`, which GitHub rejects now that Projects (classic) is deprecated. The failure is `exit 1` with no issue content at all, so it looks like a network or auth problem rather than a CLI-version problem. The REST endpoints above return the same data and are version-stable.

- **List issues**: `gh issue list --state open --json number,title,body,labels,comments --jq '[.[] | {number, title, body, labels: [.labels[].name], comments: [.comments[].body]}]'` with appropriate `--label` and `--state` filters. This one works — it uses `--json`, which does not go through the deprecated field.
- **Comment on an issue**: `gh issue comment <number> --body "..."`
- **Edit an issue body**: `gh api --method PATCH repos/Drivpe/keysteam-unlock-spike/issues/<n> -f body="$(cat file.md)"`
- **Apply / remove labels**: `gh issue edit <number> --add-label "..."` / `--remove-label "..."`
- **Close**: `gh issue close <number> --comment "..."`

Infer the repo from `git remote -v` — `gh` does this automatically when run inside a clone.

## Two directories, one project

The repository is **not** the same directory as the reverse-engineering workspace. Keep this straight:

- **Repository** — `/mnt/d/03_Work/03_Develop/keysteam-unlock-spike`. Documents, scripts, host source. This is what git tracks and what `gh` operates on.
- **Workspace** — `/mnt/d/03_Work/03_Develop/KeySteam v2.99`. Holds the sample (`KeySteam.exe`), the unpacked `main.dll`, the onefile payload copy, the data-directory backup, and the four analysis `.md` files. **Never** a git repo, never committed.

The `.gitignore` here is **deny-list shaped**: it enumerates patterns to exclude (`*.exe`, `*.dll`, `*.pyd`, `bin/`, `work/`, `*.log`, …). An earlier version of this document called it "whitelist-shaped" and claimed a sample could never be staged by accident — that was wrong on both counts, and the mistake had a concrete consequence: sample-side plugin scripts arrive as `*.lua` and `*.ks`, neither of which was on the deny list, so a `git add -A` would have committed them.

The rule is therefore: **check `git status` before `git add -A`, and never stage the workspace wholesale.** If you introduce a new artifact class from the sample side, add its pattern to `.gitignore` in the same change.


## Pull requests as a triage surface

**PRs as a request surface: no.**

Single-author private repo; there is no external contribution queue to triage.

## When a skill says "publish to the issue tracker"

Create a GitHub issue via `gh issue create`.

## When a skill says "fetch the relevant ticket"

Run `gh issue view <number> --comments`.

## Wayfinding operations

Used by `/wayfinder`. The **map** is a single issue with **child** issues as tickets.

- **Map**: a single issue labelled `wayfinder:map`, holding the Notes / Decisions-so-far / Fog body. `gh issue create --label wayfinder:map`.
- **Child ticket**: an issue linked to the map as a GitHub sub-issue (`gh api` on the sub-issues endpoint). Where sub-issues aren't enabled, add the child to a task list in the map body and put `Part of #<map>` at the top of the child body. Labels: `wayfinder:<type>` (`research`/`prototype`/`grilling`/`task`). Once claimed, the ticket is assigned to the driving dev.
- **Blocking**: GitHub's **native issue dependencies** — the canonical, UI-visible representation. Add an edge with `gh api --method POST repos/<owner>/<repo>/issues/<child>/dependencies/blocked_by -F issue_id=<blocker-db-id>`, where `<blocker-db-id>` is the blocker's numeric **database id** (`gh api repos/<owner>/<repo>/issues/<n> --jq .id`, _not_ the `#number` or `node_id`). GitHub reports `issue_dependencies_summary.blocked_by` (open blockers only — the live gate). Where dependencies aren't available, fall back to a `Blocked by: #<n>, #<n>` line at the top of the child body. A ticket is unblocked when every blocker is closed.
- **Frontier query**: list the map's open children (`gh issue list --state open`, scoped to the map's sub-issues / task list), drop any with an open blocker (`issue_dependencies_summary.blocked_by > 0`, or an open issue in the `Blocked by` line) or an assignee; first in map order wins.
- **Claim**: `gh issue edit <n> --add-assignee @me` — the session's first write.
- **Resolve**: `gh issue comment <n> --body "<answer>"`, then `gh issue close <n>`, then append a context pointer (gist + link) to the map's Decisions-so-far.
