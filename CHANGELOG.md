# Changelog

Each release's section is published as its GitHub Release notes. **Upgrade steps** always come first. Releases are cumulative, so you can upgrade straight from any older version. If you skip versions, follow every skipped version's upgrade steps, oldest first.

## v0.2.0

### Upgrade steps

This release changes the compose file. **Pulling the image alone is not enough**: download the new `docker-compose.yml` as well.

1. *(Recommended)* Take an extra backup and copy it off the server. This release also takes one automatically (see step 3).
   ```bash
   docker compose exec backup sh -c 'pg_dump --format=custom --file=/backups/christmas-before-v0.2.0.dump'
   ```
2. Replace `docker-compose.yml` with the new one. It's attached to this release, or download it:
   ```bash
   curl -fsSLO https://raw.githubusercontent.com/ashleycollinge1/christmas-list-organiser/stable/docker-compose.yml
   ```
   Your `.env` stays as it is; no settings need changing.
3. Pull and start:
   ```bash
   docker compose pull
   docker compose up -d
   ```
   The `backup` service starts first and writes `backups/christmas-<date>_startup.dump`. Only after that succeeds does `web` start and migrate the database. This takes a few seconds; `docker compose logs backup web` shows each step.
4. Check `docker compose ps`: `db`, `backup` and `web` should all be `healthy`.

There are no manual database steps. The migration runs automatically, in a single transaction.

### Database migration (0001 → 0002)

The migration only adds things. No table or column is dropped or renamed, and no existing value is changed.

- **Occasions:** the `seasons` table gains `kind` (existing rows become *Christmas*), `occasion_date` and `created_by_id` (existing rows are credited to the first admin). The "only one active season" index is removed so several occasions can be active at once; it held no data.
- **People:** a new `people` table, with each recipient linked to a person. An owner's recipients with the same name are merged into one person only when their notes and categories don't conflict; otherwise they're kept as separate people. The original `recipients.name`, `notes` and `category_id` columns are kept and stay in sync.

This was rehearsed by upgrading the released v0.1.0 stack, with real data, using the commands above. Every original row and value came through identical. The pre-upgrade dump restored cleanly.

### Rolling back

Once you've created a second active occasion, v0.1.0 can no longer run against the database. To go back, restore the `_startup.dump` taken during the upgrade, then use the v0.1.0 compose file:

```bash
docker compose stop web
docker compose exec -T db pg_restore -U xmas -d xmas --clean --if-exists --no-owner < backups/christmas-<date>_startup.dump
curl -fsSL https://raw.githubusercontent.com/ashleycollinge1/christmas-list-organiser/stable/deploy/compose/docker-compose.v0.1.0.yml -o docker-compose.yml
docker compose up -d
```

Anything entered after upgrading is lost by a rollback.

### What's new

- **Occasions replace seasons.** Christmases, birthdays and anything else ("Other"), each with an optional date and countdown. Any number can be active at once, and creating one never archives another.
- **Birthdays.** Create a birthday and bring people in. Their notes and category come with them.
- **Linked people.** A new **People** tab lists everyone you buy for. Notes and categories live on the person, so updating Molly's sizes once updates every occasion. Budgets, sharing and gifts stay per occasion. People are private to the user who added them.
- **New occasion, copied from another.** Pick an occasion to bring people in from, and choose whether to copy budgets, sharing and gifts. Copied gifts reset to Idea, with tracking, delivery date and hiding place cleared.
- **Unarchive.** Archive and unarchive any occasion you created, from its ⋯ menu or the archived banner.
- **Delete occasions.** The occasion's creator can delete it. A confirmation shows how many entries and gifts go with it. Your People are kept.
- **Per-occasion titles.** The header reads *Christmas List*, *Birthday List* or *Gift List* to match what you're looking at. Home is *Gift List*.
- **Wrapping** has an occasion picker when more than one is active.

### Changed

- **Anyone can create occasions** (previously only admins managed seasons). Renaming, archiving, unarchiving and deleting are for the creator.
- **Occasion privacy.** You see an occasion only if you created it or someone in it is shared with you. Someone can no longer spot "Ashley's birthday" in the list just because it exists. A side effect: other users no longer see archived seasons they had nobody in.
- **Shared recipients.** People you share with can edit gifts and the budget. Only you can change the person's name, notes and category.
- **Admin:** the *Seasons* tab is gone (occasions are managed on their own pages), and *People* is renamed *Accounts*.
- **Backups:** the backup service now dumps at every start, as well as nightly, and `web` waits for that dump before it starts. New optional setting: `BACKUP_REQUIRED=false` lets `web` start even if the start-up dump fails (not recommended).
- Old `#/?season=ID` links redirect to the matching occasion.

## v0.1.0

First release.
