# Christmas List Organiser

A self-hosted gift planner for the person doing the buying, for Christmases, birthdays and any other occasion. Add the people you're buying for, give each one a budget, and list their gifts. Each gift moves through a traffic light, and the app keeps a running total against every budget.

- **Budgets with a live tally.** Set a budget per person, e.g. Molly £300. Every gift has a price and quantity, and you see what you've **spent** (Ordered onwards), what you've **planned** (including ideas), and whether you're **under, on or over** budget. "On" means within a margin you choose (default ±£5).
- **Traffic-light status:** Idea → Ordered → Delivered → Wrapped → Given. A purple **Reorder** status marks a delivery that went wrong; it's listed at the top of the occasion until it's sorted. Tap a status to move it on, or press and hold to pick any stage. Every change can be undone.
- **Gift details:**
  - description, link, price and quantity
  - priority (high, medium or low)
  - retailer, tracking number (tap to copy) and expected delivery date
  - where it's hidden, and notes
- **Joint gifts.** Record "your share" of a gift you're splitting; that amount counts towards the budget instead of the full price.
- **Overview.**
  - Season totals, with people grouped by category, each with a subtotal.
  - An **Awaiting delivery** list sorted by date, showing tracking numbers.
  - A **Still to order** list sorted by priority.
- **Wrapping checklist.** Tick gifts off as you wrap them, with where each one is hidden, or print it as a paper checklist.
- **Occasions: Christmases, birthdays and more.** Any number can be active at once, each with an optional date and countdown. Start a new one from scratch, or bring people in from another occasion, optionally copying their budgets, sharing and gifts. Archive, unarchive or delete occasions; archived ones stay viewable and read-only. The header reads *Christmas List*, *Birthday List* or *Gift List* to match.
- **Search and bulk actions.** Search your wish list, people and gifts as you type. Select several items to move, archive, change status or delete them together.
- **My wish list.** Keep track of things *you'd* like, for Anytime or a specific occasion, with running totals. Archive old ideas and restore them later. Share a list as text via the iPhone share sheet, or print it.
- **Add from Safari on iPhone.** A Shortcut (set-up steps under **Account**) sends any web page to a short form. The server reads the page for the name and price; if a shop blocks that, the name is guessed from the link.
- **Linked people.** The **People** tab lists everyone you buy for. Their notes (sizes, likes) and category are shared across all their occasions, while budgets and gifts stay per occasion.
- **Private by default, shareable when needed.** Each person you add is visible only to you. Share them in an occasion with a sibling for joint gifts. Anyone you haven't shared with, admins included, can't see them, and can't see the occasion either.
- **Accounts.** The admin creates accounts, or sends single-use invite links. Passwords are hashed with Argon2id.

It's built for **iPhone Safari** (tested at iPhone 11, 12 and 14 sizes): every control is thumb-sized, and forms open as bottom sheets that stay above the keyboard. It works on desktop too.

## Architecture

```
            ┌──────── reverse proxy (TLS) ────────┐
browser ───▶│                                     │
            └─────────────┬───────────────────────┘
                          ▼
                   ┌─────────────┐        ┌──────────┐        ┌──────────────┐
                   │ web         │───────▶│ Postgres │◀───────│ backup       │
                   │ FastAPI +   │        └──────────┘        │ nightly      │
                   │ static UI   │                            │ pg_dump      │──▶ ./backups
                   └─────────────┘                            └──────────────┘
```

- **web**: the API, plus a zero-dependency HTML/CSS/JS frontend. It serves plain HTTP; your reverse proxy handles HTTPS.
- **db**: Postgres 17.
- **backup**: a `pg_dump` into a folder on the host every time it starts, then nightly. `web` waits for the start-up dump before it starts, so a backup always exists from just before any database migration. It uses the same `postgres:17-alpine` image as the database, so nothing extra is built or pulled.

## Deploy

**Nothing is built on the server.** The compose files pull a pre-built image from the GitHub Container Registry (`ghcr.io/ashleycollinge1/christmas-list-organiser`), which GitHub Actions builds on each release for `amd64` and `arm64`. Each compose file is pinned to that release's image digest.

| File | Use it for |
|---|---|
| `docker-compose.yml` (repo root) | The current release. Updated automatically by each release. |
| `deploy/compose/docker-compose.vX.Y.Z.yml` | Pinning or rolling back to a specific version. |
| `docker-compose.dev.yml` | Local development only. Builds from source. |

On the host you only need two files, `docker-compose.yml` and `.env`:

```bash
mkdir christmas-list && cd christmas-list
curl -fsSLO https://raw.githubusercontent.com/ashleycollinge1/christmas-list-organiser/stable/docker-compose.yml
curl -fsSL  https://raw.githubusercontent.com/ashleycollinge1/christmas-list-organiser/stable/.env.example -o .env
nano .env                      # set POSTGRES_PASSWORD and ADMIN_PASSWORD (12+ characters)
docker compose pull
docker compose up -d
```

Then point your reverse proxy at `127.0.0.1:8000` and sign in as `ADMIN_USERNAME`.

> The root `docker-compose.yml` is generated by the first release (see [Releases](#releases-cicd)). Until a version has been tagged, it doesn't exist yet.

### Reverse proxy

The app speaks plain HTTP and trusts `X-Forwarded-*` headers from the proxy.

**Caddy**

```caddy
gifts.example.com {
    reverse_proxy 127.0.0.1:8000
}
```

**nginx**

```nginx
location / {
    proxy_pass http://127.0.0.1:8000;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
}
```

**Traefik / a proxy in Docker:** remove the `ports:` mapping, attach `web` to the proxy's network, and target `web:8000`.

### Network access & login cookies

| How people reach the app | `APP_BIND` | `COOKIE_SECURE` |
|---|---|---|
| `https://…` via a reverse proxy **on the same host** (not in Docker) | `127.0.0.1` *(default)* | `true` *(default)* |
| `https://…` via a reverse proxy **on another machine** | `0.0.0.0`, or that host's LAN IP | `true` |
| `https://…` via a proxy **in Docker** on the same host | Not needed: use the proxy's network | `true` |
| `http://<host>:<port>` directly (LAN or testing only) | `0.0.0.0`, or the LAN IP | **`false`** |

Docker-published ports bypass `ufw` on most Linux hosts. If you use `0.0.0.0` on an internet-facing machine, firewall it at the router or cloud level.

| Symptom | Cause | Fix |
|---|---|---|
| Containers are healthy, but the page won't load from another machine | `APP_BIND=127.0.0.1` (the default) | Set `APP_BIND=0.0.0.0` or the LAN IP |
| *"Your session ended. Please sign in again."* straight after every login | `COOKIE_SECURE=true` while browsing over `http://` | Use the `https://` address, or set `COOKIE_SECURE=false` on a trusted LAN |
| `docker compose up -d` sits at *"Waiting"* and `web` stays *Created* | The start-up backup is failing, so `web` (which migrates the database) is held back on purpose | Run `docker compose logs backup` and fix the cause (often disk space or folder permissions on `BACKUP_PATH`). In an emergency only, set `BACKUP_REQUIRED=false` |

### Configuration

All settings are environment variables in `.env`. See [`.env.example`](.env.example) for the annotated list.

| Variable | Default | Notes |
|---|---|---|
| `POSTGRES_PASSWORD` | *(required)* | |
| `ADMIN_USERNAME` / `ADMIN_PASSWORD` | `admin` / — | Used **only on first start** to create the admin. Changing them later has no effect. |
| `APP_BIND` / `APP_PORT` | `127.0.0.1` / `8000` | Host address and port for the web UI. |
| `COOKIE_SECURE` | `true` | Must be `false` if you browse over plain `http://`. |
| `BACKUP_PATH` | `./backups` | Host folder for nightly dumps. |
| `BACKUP_TIME` | `03:00` | Local time of the nightly backup (24h, in `TZ`). |
| `BACKUP_KEEP_DAYS` | `30` | Older dumps are deleted. |
| `BACKUP_UID` / `BACKUP_GID` | `1000` | Owner of the dump files on the host. |
| `BACKUP_REQUIRED` | `true` | `web` only starts after a successful start-up dump. `false` lets it start anyway (not recommended). |
| `TZ` | `Europe/London` | |

The budget margin ("on budget" means within ±£5) and categories are managed in the app's **Admin** tab, not in `.env`.

### Backups & restore

The `backup` service writes pg_dump custom-format files into `BACKUP_PATH`:

- `christmas-YYYY-MM-DD_HHMMSS_before-vX.Y.Z.dump` on the first start of each new version, i.e. just before that version migrates the database. These are **kept permanently** (never pruned): they're what a rollback restores. Every release changes the backup service's configuration, so upgrading always recreates it, and `web` (which runs migrations) waits until this dump has succeeded.
- `christmas-YYYY-MM-DD_HHMMSS_startup.dump` on every other start.
- `christmas-YYYY-MM-DD_HHMMSS_nightly.dump` every night at `BACKUP_TIME`.

Start-up and nightly dumps older than `BACKUP_KEEP_DAYS` are deleted. Check it with `docker compose logs backup`. If the start-up dump fails, `web` won't start: the log says why. Fix the problem, or set `BACKUP_REQUIRED=false` in an emergency.

Take a backup right now:

```bash
docker compose exec backup sh -c 'pg_dump --format=custom --file=/backups/christmas-manual-$(date +%F).dump'
```

Restore one. This replaces **all** current data with the backup:

```bash
docker compose stop web
docker compose exec backup restore-backup christmas-2026-12-01_030000_nightly.dump
docker compose up -d
```

`restore-backup` checks the file is readable and saves the current data as `christmas-<date>_before-restore.dump`. It then rebuilds the database from the backup in a single transaction: either it fully succeeds, or nothing changes. Run it with no arguments to list the available backups.

If the backup came from an **older version**, start that version afterwards (its compose file is in `deploy/compose/`). A newer version would simply migrate it forward again. Copy the backups folder somewhere off the server too.

### Upgrading

**Read the [release notes](https://github.com/ashleycollinge1/christmas-list-organiser/releases) first.** Every release lists its upgrade steps at the top, followed by any database changes and how to roll back. They're also in [`CHANGELOG.md`](CHANGELOG.md).

The usual steps are to replace `docker-compose.yml` with the new one (attached to each release), then:

```bash
docker compose pull
docker compose up -d
```

The backup service takes a `_before-vX.Y.Z.dump` snapshot first. Then `web` starts and runs any database migrations automatically. To roll back, restore that snapshot with `restore-backup` and use the previous version's compose file from `deploy/compose/`; the release notes give the exact commands.

## Using it

1. **Admin → Categories** (optional): add groups such as *Kids* or *Siblings*. People without one appear under *Uncategorised*.
2. **Open an occasion → Add person**: pick one of your people or add someone new, then set a budget and who to share with.
3. **Add gift**: only the description is required. Fill in price, link and the rest as you go.
4. **Tap the status pill** to move a gift on as you order it, it arrives, and you wrap it. Press and hold the pill to pick any stage.
5. **Wrapping**: tick gifts off as you wrap them. The printer button gives you a paper copy.
6. **Home → New occasion** for a birthday or next Christmas. Pick people (and optionally an occasion to copy budgets, sharing and gifts from). Use an occasion's ⋯ menu to edit, archive, unarchive or delete it.

Inviting someone: **Admin → Accounts → Invite link**, then *Share…* sends it straight to Messages on an iPhone. Each link works once and expires after 7 days.

## Releases (CI/CD)

- **Every push to `stable` and every PR** runs lint, the tests against a real Postgres, and a test Docker build ([`ci.yml`](.github/workflows/ci.yml)).
- **Pushing a tag**, e.g. `git tag v1.0.0 && git push origin v1.0.0`, runs [`release.yml`](.github/workflows/release.yml). It:
  1. checks [`CHANGELOG.md`](CHANGELOG.md) has a `## v1.0.0` section with `### Upgrade steps`, and stops if not; then runs the tests;
  2. builds the image for `linux/amd64` and `linux/arm64`, and pushes it to `ghcr.io/ashleycollinge1/christmas-list-organiser` tagged `1.0.0`, `1.0`, `latest` and `sha-…`;
  3. renders [`deploy/compose.template.yml`](deploy/compose.template.yml) into `deploy/compose/docker-compose.v1.0.0.yml` pinned to the image **digest**, updates `docker-compose.latest.yml` and the root `docker-compose.yml`, and commits them to `stable`.

  4. publishes a **GitHub Release** for the tag, with that changelog section as its notes and the version's compose file attached.

Pre-release tags (`v1.1.0-rc.1`) get their own compose file and a pre-release, but don't move `latest` or the root file.

**First release only:** open the package on GitHub (*Packages → christmas-list-organiser → Package settings*) and check its visibility is **Public**. Packages pushed from a public repo's workflow usually inherit public visibility, but a new package can start out private. Once it's public, anyone can `docker compose pull` without logging in. If `stable` is branch-protected, allow GitHub Actions to push to it.

To change what gets deployed, edit `deploy/compose.template.yml`, not the generated files.

## Making changes safely

This is production software with real data. Every change follows these rules:

- **Migrations are additive.** Add tables and columns; never drop, rename or rewrite existing data in a migration. If something must go, stop using it and leave it in place.
- **Every migration gets a data-preservation test** in [`tests/test_migrations.py`](tests/test_migrations.py): seed the previous schema with realistic data, upgrade, and check that every row and value survived.
- **CI runs `alembic check`**, so model changes can't ship without a matching migration.
- **Every release has a `CHANGELOG.md` entry** with **Upgrade steps** first, including any manual or migration steps and how to roll back. The release workflow refuses to publish without one.
- Work on a branch and open a pull request, so CI runs before anything reaches `stable`.

## Development

```bash
docker compose -f docker-compose.dev.yml up --build   # http://localhost:8000  (admin / change-me-please)
```

Tests need a Postgres instance:

```bash
docker run -d --name xmas-test-pg -e POSTGRES_USER=xmas -e POSTGRES_PASSWORD=xmas -e POSTGRES_DB=xmas \
  -p 127.0.0.1:55433:5432 postgres:17-alpine
python -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
.venv/bin/pytest -q
.venv/bin/ruff check . && .venv/bin/ruff format --check .
```

Override the database with `DATABASE_URL=postgresql+psycopg://user:pass@host:port/db`.

### Layout

```
app/            FastAPI app: models, budget maths, routers (auth, users, admin, lists)
alembic/        database migrations (run automatically on start)
frontend/       zero-dependency UI: index.html, css/, js/ (ES modules), fonts/
deploy/         compose template; generated per-release compose files in deploy/compose/
scripts/        generate_compose.py, used by the release workflow
docker/         container entrypoint
```

## Licence

[MIT](LICENSE). The fonts are under the SIL Open Font License (see [`frontend/fonts/README.md`](frontend/fonts/README.md)).
