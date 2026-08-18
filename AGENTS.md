# NameMachine operating rules

These rules apply to every human or automated session that changes this repository
or its Railway deployment.

## Canonical production target

- GitHub repository: `mvsamarskiy-cmd/Find-back-ip`
- Deployment branch: `main`
- Railway workspace: `0322601c-7680-4bdd-ae2c-c27dd77710df`
- Railway project: `resourceful-stillness` (`ba6f4d56-5ad6-4ad2-be1d-816c3c7d7a88`)
- Railway environment: `production` (`d08602f0-0919-41d0-97b7-8383278c70ee`)
- Railway service: `web` (`50ce503c-aa4d-4ecd-91e6-e80d940afe71`)
- Production URL: `https://web-production-04fec.up.railway.app`

`ops/railway-production.json` is the machine-readable source of truth for these
values. A different Railway project is not a replacement production target.

## Mandatory workflow

1. Run `python verification/railway_guard.py show` at the start of a session.
2. Before any Railway command, run `python verification/railway_guard.py link`.
   This links the local directory to the exact project, environment, and service
   IDs above.
3. Never run `railway init`, create a new Railway project, or attach this GitHub
   repository to another Railway project.
4. Make code changes on one short-lived `agent/*` branch. Never edit `main`
   directly and never split one logical release into several direct commits.
5. Open one pull request, require green CI, and squash-merge it into one release
   commit.
6. Use local tests and GitHub CI for ordinary verification. If a live preview is
   required, use a temporary PR environment inside `resourceful-stillness`; never
   create a separate Railway project. PR environments must disappear when the PR
   is merged or closed.
7. Production may deploy only from `main`. Enable Railway **Wait for CI** so a
   failed GitHub workflow skips deployment.
8. After deployment, run `python verification/railway_guard.py smoke` and confirm
   Railway reports the same Git commit as GitHub `main`.
9. If the current release breaks production, restore code with Git history: use
   the manual `Prepare production rollback PR` workflow. It reverts exactly the
   current `main` release, proves that the restored tree equals the previous
   release, runs the release verification commands, and only then pushes a
   temporary `agent/rollback-*` branch and opens a PR. Never reset or force-push
   `main`; merge the verified rollback normally and run the same production smoke
   check after deployment.
10. Run `python verification/railway_guard.py audit` whenever Railway access is
    established. It reports other projects attached to this repository but never
    deletes them automatically.
11. A duplicate may be deleted only after confirming that the canonical site is
    healthy and that the duplicate has no unique variables, volumes, buckets, or
    custom domains.

Git history is the lightweight backup for application code only. It does not
back up Railway secret values, databases, volumes, buckets, or external-service
state; those require separate backup once the project stores persistent data.

Do not commit `.railway/` or credentials. Railway documents that the CLI link is
local state, so every new session must recreate it with the exact canonical IDs.
