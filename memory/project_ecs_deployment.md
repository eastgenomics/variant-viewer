---
name: ECS deployment, Docker, and Next.js gotchas
description: Hard-won lessons on ECS health checks, HOSTNAME binding, Docker builds, ECS Exec, and Next.js static rendering
type: project
---

## Docker / ECR

- User may not be in the `docker` group. Fix: `sudo usermod -aG docker $USER && newgrp docker`.
- Background shell sessions don't pick up new group; use `sg docker -c "docker build ..."`.
- `public/` directory must exist (even as `.gitkeep`) — Dockerfile COPY fails without it.
- Always check `tsconfig.lambda.json` compiles cleanly before building.
- Need `@types/aws-lambda` as devDependency for Lambda TypeScript compilation.

## ECS Health Check

- **Use `CMD` not `CMD-SHELL`**: `["CMD", "node", "-e", "<js>"]` avoids shell quoting issues in Alpine sh.
- `startPeriod` should be **60s** — Next.js standalone can take >30s to start on low-CPU Fargate.
- With `retries=3, interval=30, startPeriod=30` the container is killed at ~2 min (matches cycling pattern).
- **`HOSTNAME=0.0.0.0` is required** in ECS task env. Next.js 15 standalone binds to the container's internal hostname by default, not `0.0.0.0`. Health check hits `localhost:3000` which won't be listening without this.

## Next.js Static Rendering Gotcha

- Server Components that query the DB but use no dynamic functions (`cookies()`, `headers()`) are **statically pre-rendered at build time**.
- Build has no DB -> error is baked into the static HTML -> users always see DB error.
- **Fix**: add `export const dynamic = "force-dynamic"` to any page that needs live DB data.
- Confirmation in build output: `f` prefix = dynamic, `o` prefix = static.
- `force-dynamic` is correct for pages using raw `node-postgres` queries — fetch-level caching only applies to the Next.js `fetch()` wrapper.

## ECS Exec

- Requires `enable_execute_command = true` on ECS service AND `ssmmessages:*` IAM permissions on task role.
- Session Manager plugin must be installed locally (`session-manager-plugin`).
- Tasks started before the service update don't get exec enabled — force a new deployment.

**Why:** Each of these caused container cycling, blank pages, or failed deploys during first deployment.

**How to apply:** Reference before any ECS/Docker changes. The HOSTNAME and force-dynamic issues are the most non-obvious.
