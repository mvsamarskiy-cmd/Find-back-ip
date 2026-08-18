# Railway production runbook

## Why this exists

Connecting the same GitHub repository through Railway's **New Project** flow
creates another independent project and another automatic deployment trigger.
That is how one Git push was multiplied across many services. The repository
cannot prevent Railway's dashboard from creating a project, so the prevention
mechanism is an explicit canonical manifest, agent rules, a target-linking guard,
workspace auditing, and automatic cleanup of short-lived Git branches.

## One permanent Railway project

Production is always `resourceful-stillness`. The exact IDs are stored in
`ops/railway-production.json`. Never choose **New Project** for this repository.

Railway stores `railway link` state in a local `.railway` directory, which is
normally ignored by Git. A new device or agent therefore recreates the link with:

```bash
python verification/railway_guard.py link
```

The guard invokes `railway link` with the canonical project, environment, and
service IDs. It does not create infrastructure.

## Change path

1. Update local `main` from GitHub.
2. Create one `agent/<change>` branch.
3. Make one coherent change and update tests and documentation in that branch.
4. Run:

   ```bash
   python -m unittest discover -s tests -v
   python verification/check_inline_js.py
   gunicorn app:app --config gunicorn.conf.py --check-config
   ```

5. Open one PR and wait for green CI.
6. Use squash merge, producing one commit on `main` and therefore one production
   build.
7. Railway deploys `main` only after GitHub CI passes.
8. Run `python verification/railway_guard.py smoke`.

Do not commit a series of file-by-file changes directly to `main`: every such
commit is a separate Railway deployment.

## Lightweight code backup and rollback

Git history is the backup for application code. Because normal releases are
squash-merged, one logical release is one commit on `main`. Do not create backup
copies of the repository, permanent shadow branches, or duplicate Railway
projects just to preserve code.

If the newest release breaks production:

1. In GitHub Actions run **Prepare production rollback PR**.
2. The workflow checks out the current `main` and locally reverts exactly that
   release.
3. Before anything is pushed, it verifies that the reverted Git tree is exactly
   the previous release tree and runs unit tests, inline-JavaScript validation,
   and the Gunicorn config check. If any check fails, no rollback branch is
   published.
4. Only after verification does it push a temporary `agent/rollback-*` branch and
   open a pull request. Review it and satisfy any repository-required checks.
5. Never reset or force-push `main`. Merge the rollback normally so Railway gets
   one auditable recovery commit.
6. After Railway deploys it, run `python verification/railway_guard.py smoke`.
7. Close/merge the PR normally; the existing branch-cleanup workflow removes the
   temporary rollback branch.

This deliberately uses a Git **revert**, not a history rewrite, so both the bad
release and its recovery remain auditable and recoverable.

This is only a code rollback. Git does **not** back up Railway secret values,
databases, volumes, buckets, user data, or external-service state. Add separate
backups before any such persistent state becomes production-critical.

## Verification without permanent clones

Ordinary changes are verified by tests and GitHub Actions. When a live copy is
necessary, enable Railway PR environments in the canonical project. Railway
creates the environment for the PR and deletes it when the PR is merged or
closed. This is a temporary environment inside the same project, not another
project.

Before enabling PR environments, close obsolete PRs so Railway does not create
previews for historical branches. Keep `production` bound to `main`.

## Connection-time audit

With a Railway user/OAuth API token in `RAILWAY_API_TOKEN`, run:

```bash
python verification/railway_guard.py audit
```

The audit reads only project/resource metadata. It reports every other project
whose service points to `mvsamarskiy-cmd/Find-back-ip`, including variable names,
volume count, bucket count, custom domains, and deployment status. It never reads
variable values and never deletes anything.

The command exits non-zero if a shadow project exists, so a session cannot
silently declare the workspace clean.

## Deletion gate

A shadow Railway project may be deleted only when all checks are true:

- its ID is not the canonical project ID;
- every service source is the canonical GitHub repository;
- it has no unique variable names;
- it has no volumes or buckets;
- it has no custom domain;
- canonical production is healthy;
- the deployed canonical commit equals GitHub `main`;
- the exact project name and ID were reviewed immediately before deletion.

Deletion remains a deliberate external operation; it is intentionally absent
from `railway_guard.py`.

## Railway settings to keep enabled

- GitHub deployment branch: `main`.
- **Wait for CI**: enabled.
- Health-check path: `/health`.
- Config-as-code file: `railway.json`.
- PR environments: optional, but only inside `resourceful-stillness` and only
  after obsolete PRs are closed.

Official Railway references:

- https://docs.railway.com/cli/link
- https://docs.railway.com/deployments/github-autodeploys
- https://docs.railway.com/environments
- https://docs.railway.com/config-as-code/reference
