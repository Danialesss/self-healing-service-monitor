<!--
This specification defines the project goals and the order in which work
should be built. It is a planning document for the full service-monitoring
system.
-->

# Self-healing service monitor

<!--
The overall goal is simple: keep a production service running by detecting
problems early and recovering automatically before a customer notices.
-->

## The problem

A small company runs an API in production. Sometimes it degrades, a memory
leak builds up, a percentage of requests start hanging, or it crashes
outright. Normally a human only finds out when a customer complains, or
when someone happens to check the logs. This project is the fix: a system
that watches a running service, detects when it goes unhealthy, tries to
recover it automatically by restarting it, and emails a human exactly what
happened and what was done about it. Detection, remediation, and
notification, working together, with no person needed in the loop for the
common case.

## Why it exists

This proves cloud operations skills that a pure API/integration project
does not: standing up real infrastructure in Azure, running a background
process that takes autonomous action, and handling the failure modes of
that action responsibly (not restarting forever, not flapping, always
telling a human what happened).

## Architecture

Four independent pieces, each its own small service:

1. **flaky-app** — a tiny FastAPI app that is the thing being watched. It
   has a normal `/health` endpoint, and a few endpoints/background
   behaviors that deliberately misbehave on command or at random, so
   failures can be demonstrated reliably rather than waited for.
2. **watcher** — polls `flaky-app`'s health every N seconds. Tracks state
   (healthy / unhealthy / recovering). When it decides the app is down,
   it raises an incident.
3. **remediator** — when an incident is raised, restarts the flaky-app's
   Azure Container App via the Azure SDK/CLI. Enforces a cooldown and a
   max-restarts-per-hour limit so it cannot loop forever if the app is
   truly broken (that case should escalate to a human instead of retrying
   forever).
4. **notifier** — sends an email when an incident starts (what broke,
   when) and when it resolves (what was done, how long it took).

A simple incident log (append-only file or small database table) records
every incident: start time, cause, action taken, resolution time. This
becomes the dashboard/history and the evidence for a portfolio writeup.

```
flaky-app  <---poll--- watcher ---detects incident---> remediator ---restarts---> Azure Container App
                                        |
                                        +---writes---> incident log
                                        |
                                        +---triggers---> notifier ---emails---> you
```

## Failure modes to build into flaky-app (pick 2, not all 3, to keep scope sane)

- **Memory leak mode**: an endpoint that, once hit, starts allocating memory
  in a background loop until the app slows or is OOM-killed.
- **Random hang mode**: a percentage of requests to a given endpoint sleep
  for a long time or never return, simulating a stuck dependency.
- **Manual chaos endpoint**: `/chaos/crash` that force-exits the process
  immediately, useful for live, on-demand demos.

Recommended for v1: memory leak (shows gradual degradation, detectable via
a metrics threshold) + manual chaos endpoint (reliable, instant demo).
Random hang can be a stretch addition.

## Tech stack

- **Language**: Python (FastAPI for flaky-app, plain Python or FastAPI for
  watcher/remediator/notifier)
- **Containerization**: Docker for every piece
- **Cloud**: Azure Container Apps (target of deployment and of restarts),
  Azure Container Registry for images
- **Restart mechanism**: Azure CLI (`az containerapp revision restart` or
  equivalent) called from the remediator, authenticated via a service
  principal (do not use personal credentials)
- **Email**: any SMTP-based sender (e.g. a free-tier transactional email
  service) called from notifier
- **CI/CD**: GitHub Actions, build and push images, deploy on push to main
- **Incident log**: start with a flat JSON-lines file or SQLite; a real
  database is not required for v1
- **Observability (stretch)**: Datadog agent on the container, dashboard
  panel showing incident count over time, using the GitHub Student Pack
  Datadog offer

## Prerequisites before opening this in Copilot

- [ ] Azure for Students credit active, subscription ID in hand
- [ ] Azure CLI installed and logged in (`az login`) in the dev environment
- [ ] A service principal created for the remediator to use (not personal
      login), scoped only to the resource group this project uses
- [ ] Azure Container Registry created
- [ ] An SMTP/email sending account (free tier is fine) and its credentials
      available as environment variables/secrets, never committed
- [ ] Docker available in the dev environment
- [ ] GitHub repo created for this project (separate from Job Board MCP and
      Ticket Triage)

## Build phases

Each phase should be independently runnable and testable before moving to
the next. Do not let Copilot skip ahead to later phases before earlier
ones are verified working.

**Phase 1 — flaky-app, running locally**
Build the FastAPI app with `/health`, the memory-leak endpoint, and
`/chaos/crash`. Verify locally: hit `/health` (should be fine), trigger the
leak and watch memory/response time degrade, hit `/chaos/crash` and confirm
the process exits. Dockerize it. Acceptance: `docker run` it, curl all
three endpoints, behavior matches spec.

**Phase 2 — deploy flaky-app to Azure**
Push the image to Azure Container Registry, deploy to Azure Container
Apps. Confirm you can reach `/health` over the public URL, and that
`/chaos/crash` actually kills the running revision (and Azure restarts it
on its own by default, note that baseline behavior before adding your own
remediator on top). Acceptance: public URL responds, all three endpoints
work identically to local.

**Phase 3 — watcher**
Build the polling loop against the deployed URL. Define what "unhealthy"
means precisely (no response within X seconds counts as N consecutive
failures before declaring an incident, to avoid false positives from one
network blip). Log incidents to the incident log. Acceptance: manually
trigger `/chaos/crash`, watcher detects it within its polling interval and
logs an incident with a timestamp and reason.

**Phase 4 — remediator**
Wire the watcher's incident detection to a call that restarts the Azure
Container App via the Azure SDK/CLI, using the service principal.
Implement the cooldown and max-restarts-per-hour guard. Acceptance:
trigger a crash, confirm the app is automatically restarted without manual
intervention, confirm a second rapid crash within the cooldown window does
NOT trigger another restart attempt (it should escalate/log instead).

**Phase 5 — notifier**
Send an email on incident start and on resolution, with the relevant
details (what broke, when, what action was taken, how long recovery
took). Acceptance: trigger an incident, receive both emails, content is
accurate.

**Phase 6 — CI/CD**
GitHub Actions workflow: build and push each Docker image, deploy to Azure
Container Apps on push to main. Reuse patterns from the Job Board MCP
pipeline. Acceptance: a push to main results in a fresh deployment with no
manual steps.

**Phase 7 — incident history / polish**
A simple way to view incident history (a small endpoint returning the log
as JSON is enough; a basic HTML page or a Datadog dashboard panel is a
nice stretch). Write the README the same way as Ticket Triage: what it
does, what you found when you tested it (a real triggered incident with
timestamps), what you learned, honest limitations. Record a short demo
(trigger a crash live, show the recovery and the email) for the portfolio.

## Guardrails worth stating explicitly (for Copilot too)

- Never let the remediator restart in an unbounded loop. A cooldown and a
  hard cap per hour are not optional.
- Never commit Azure credentials, service principal secrets, or email
  credentials. Use environment variables and GitHub Actions secrets.
- The service principal used for restarts should be scoped as narrowly as
  possible (this resource group only), not a subscription-wide owner role.
- Keep flaky-app, watcher, remediator, and notifier as separate,
  independently deployable pieces, not one monolith script. That
  separation is itself part of what this project is meant to demonstrate.

## What "done" looks like

You can trigger a failure on demand, watch the system detect it, restart
the service automatically, receive an email explaining what happened, and
pull up a log showing every incident that has ever occurred, all backed by
a CI/CD pipeline that deploys the whole thing on every push.
