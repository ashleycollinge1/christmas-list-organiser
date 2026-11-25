# Changelog

Each release's section is published as its GitHub Release notes. **Upgrade steps** always come first. Releases are cumulative, so you can upgrade straight from any older version. If you skip versions, follow every skipped version's upgrade steps, oldest first.

## v0.5.0

### Upgrade steps

1. Replace `docker-compose.yml` with the new one (attached to this release, or `curl -fsSLO https://raw.githubusercontent.com/ashleycollinge1/christmas-list-organiser/stable/docker-compose.yml`).
2. `docker compose pull && docker compose up -d`

No database changes, so no migration. To roll back, use the v0.4.1 compose file and `docker compose up -d`; no restore is needed.

### What's new

- **Occasions for yourself.** In **New occasion → Who's it for?**, tick **Me (my wish list)** at the top.
  - With Birthday selected, the name suggests itself, e.g. *"Ashley's birthday 2027"*.
  - **Bring in my Anytime wishes** lists your Anytime wishes, all ticked. Ticked ones move into the new occasion; untick any you want to keep in Anytime. You can move them back later, in bulk if you like.
  - You can tick Me *and* other people, e.g. for a joint birthday.
- **An occasion that's just for you leads with your wish list:** every wish, the total, Share, and *Add a wish*. There's no empty budget, and a small *Add a person* link if you're buying for someone too. On Home, its card shows *My wish list · 2 wishes · £40*.

### Changed

- The *My wish list* card on an occasion page still shows your top three; the full list is one tap away.

## v0.4.1

### Upgrade steps

1. Replace `docker-compose.yml` with the new one (attached to this release, or `curl -fsSLO https://raw.githubusercontent.com/ashleycollinge1/christmas-list-organiser/stable/docker-compose.yml`).
2. `docker compose pull && docker compose up -d`

No database changes, so no migration. To roll back, use the v0.4.0 compose file and `docker compose up -d`; no restore is needed.

### Fixed

- **The Wrapping checklist only lists gifts you actually have:** Delivered, Wrapped and Given. Ordered and Reorder gifts are left off until they're marked Delivered, and a line says how many are still on their way. Previously, tapping *N delivered* on an occasion opened a checklist that also included undelivered gifts.

## v0.4.0

### Upgrade steps

Same routine as before: new compose file, then pull and start.

1. Replace `docker-compose.yml` with the new one. It's attached to this release, or download it:
   ```bash
   curl -fsSLO https://raw.githubusercontent.com/ashleycollinge1/christmas-list-organiser/stable/docker-compose.yml
   ```
   Your `.env` stays as it is.
2. Pull and start:
   ```bash
   docker compose pull
   docker compose up -d
   ```
   The `backup` service first writes `backups/christmas-<date>_before-v0.4.0.dump`, kept permanently, then `web` starts and migrates.
3. Check `docker compose ps`: `db`, `backup` and `web` should all be `healthy`.

There are no manual steps and no new settings.

### Database migration (0003 → 0004)

The migration adds **Reorder** to the list of allowed gift statuses. It replaces the status check with a wider one in a single transaction. No data is touched.

This was rehearsed by upgrading the released v0.3.0 stack, with data, using the commands above. Every table came through identical. The rollback below was also rehearsed, and restored the v0.3.0 state exactly.

### Rolling back

```bash
docker compose stop web
docker compose exec backup restore-backup christmas-<date>_before-v0.4.0.dump   # your file's name from ./backups
curl -fsSL https://raw.githubusercontent.com/ashleycollinge1/christmas-list-organiser/stable/deploy/compose/docker-compose.v0.3.0.yml -o docker-compose.yml
docker compose up -d
```

Anything changed since the upgrade is lost, but `restore-backup` first saves it as `christmas-<date>_before-restore.dump`.

### What's new

- **Search.** A search box on your wish list (it also finds archived ideas), on each person's page, on each occasion page (across everyone's names and gifts), and on People. It matches names, notes, shops, tracking numbers and hiding places as you type.
- **Select several at once.** Tap **Select** to tick items, or use **Select all**, then:
  - **Wish list:** Move to Anytime or an occasion, Archive or Restore, Delete.
  - **A person's gifts:** Set status, Move to the same person in another occasion (they're added there if needed), Delete.

  Deleting asks first. Every change is all or nothing.
- **Reorder status** (purple) for a delivery that went wrong or an item that arrived damaged.
  - Set it by holding the status pill, in the gift form, or with Set status.
  - Tapping it moves the gift back to **Ordered** once the replacement is on its way.
  - Reorder gifts count as spent, sort to the top of a person's list, and appear in a **Needs reordering** list at the top of the occasion page.
- **More counts on an occasion page:** *people · to reorder · to order · awaiting · delivered · wrapped*. Delivered and Wrapped open that occasion's Wrapping checklist.
- **Sharing on a computer.** **Share** now opens a window showing the text, with **Copy** and **Download .txt**. iPhone and iPad still use the share sheet.

### Changed

- The status picker in the gift form is now two rows of three, to fit Reorder.
- The Wrapping checklist lists Reorder gifts as *Being reordered*.

## v0.3.0

### Upgrade steps

Same routine as v0.2.0. Each release's compose file pins its exact image, so download the new one too.

1. Replace `docker-compose.yml` with the new one. It's attached to this release, or download it:
   ```bash
   curl -fsSLO https://raw.githubusercontent.com/ashleycollinge1/christmas-list-organiser/stable/docker-compose.yml
   ```
   Your `.env` stays as it is; no settings need changing.
2. Pull and start:
   ```bash
   docker compose pull
   docker compose up -d
   ```
   The `backup` service starts first and writes **`backups/christmas-<date>_before-v0.3.0.dump`**, a snapshot of your data from just before the upgrade. Then `web` starts and migrates. That file is kept permanently (it's never auto-pruned) and is what you'd restore to roll back.
3. Check `docker compose ps`: `db`, `backup` and `web` should all be `healthy`.
4. *(Optional)* Set up the iPhone Shortcut: **Account → iPhone Shortcut** lists the steps, with your server's address filled in.

There are no manual database steps.

**New network requirement (optional feature):** filling in a name and price from a shared link means the `web` container fetching that page from the internet. If your server blocks outbound internet, everything else still works and you type the details yourself.

### Database migration (0002 → 0003)

The migration only adds things. No table or column is dropped or renamed, and no existing value is changed.

- `people` gains `kind`; every existing person becomes `recipient` (someone you buy for). A new index allows at most one `me` person per account.
- New `wishes` table. If an occasion is deleted, its wishes move to *Anytime* rather than being deleted.

This was rehearsed by upgrading the released v0.2.0 stack, with data, using the commands above. Every original row and value came through identical. The rollback below was rehearsed too, and restored the v0.2.0 state exactly.

### Rolling back

An older version can't start against a database a newer one has migrated. So rolling back means restoring the snapshot taken just before the upgrade, then using the old compose file. Anything entered since the upgrade (e.g. new wishes) is lost, but a safety copy of it is kept.

```bash
docker compose stop web
docker compose exec backup restore-backup christmas-<date>_before-v0.3.0.dump   # use your file's name from ./backups
curl -fsSL https://raw.githubusercontent.com/ashleycollinge1/christmas-list-organiser/stable/deploy/compose/docker-compose.v0.2.0.yml -o docker-compose.yml
docker compose up -d
```

`restore-backup` first saves the current data as `christmas-<date>_before-restore.dump`. It then replaces the database in a single transaction, so if anything goes wrong nothing has changed. If you start an older version against a newer database by mistake, its log now says so plainly, instead of restarting in a loop.

### What's new

- **My wish list.** Keep track of things *you'd* like: for **Anytime**, or for a specific birthday, Christmas or other occasion. Move ideas between lists whenever you like.
  - Each wish has a description, link, price and quantity, *how much you want it* (Really want / Would like / Nice to have), and notes such as size or colour.
  - The list shows a running total (*"8 wishes · £412"*), overall and per list.
  - **Archive** ideas you've had or gone off. They stay under *Archived ideas*, ready to restore when you're stuck for ideas.
  - **Share** a list (or the whole thing) as tidy text through the iPhone share sheet, ready for Messages or WhatsApp, or **print** it. Your *Sizes & notes* are included.
  - Wishes are private and never count towards budgets, spending, ordering or wrapping.
- **"Me" person type.** Your wish list appears first on **People**. A new person can be *Someone I buy for* or *Me*, one per account. It's created automatically when you add your first wish.
- **Occasion pages** show a *My wish list* card with your wishes for that occasion, and an *Add a wish* button.
- **iPhone Shortcut: add from Safari's Share button.** Share any page to *Add to wish list* and a short form opens with the link filled in. The server reads the page to suggest the name and price, then you check it and tap *Add*.
  - If you're signed out, you sign in once inside the window and land back on the form.
  - Some shops (Argos, for example) block automated reading. The form then suggests a name taken from the link, or you type one.
  - Links inside shared text ("Check this out https://…") are picked out automatically.
  - Reading is restricted to public websites. Private, local and internal network addresses are refused, including after redirects. There are time and size limits, and a per-user rate limit.

### Changed

- **Backups and restore (important if you ever restore):**
  - The first start of each new version keeps a named snapshot, `christmas-<date>_before-vX.Y.Z.dump`, which is never pruned.
  - New one-step, all-or-nothing restore: `docker compose exec backup restore-backup <file>`.
  - **The restore command in the v0.2.0 notes and README (`pg_restore --clean …`) could only partly restore a backup taken by an older version**, leaving a mix of old and new data. Don't use it; use `restore-backup` instead.
- Deleting an occasion now says how many of your wishes will move back to *Anytime*.
- *Me* can't be added to an occasion as someone you buy for. Add wishes instead.

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

> **Correction (found while preparing v0.3.0):** the `pg_restore --clean` command above can only partly restore a backup taken by an older version. Tables that only exist in the newer version block the old ones from being replaced, leaving a mix of old and new data. From v0.3.0 onwards, use the all-or-nothing `docker compose exec backup restore-backup <file>`, which restores backups from any version correctly.

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
