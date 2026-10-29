# Deployment


## 1. Platform choice
- **Streamlit Community Cloud** hosts the app free, straight from GitHub, with a shareable HTTPS URL.
- **Neon (PostgreSQL)** holds the data, because Community Cloud's disk is not a safe place for investigation history.
- Same codebase either way; `DATABASE_URL` picks the database.

Check current plan limits before relying on them. At the time of writing, Neon Free offered 0.5 GB per project and suspends idle
compute after 5 minutes (first request afterwards is slower). This project needs a few MB.

## 2. Create the hosted database
1. Sign up at neon.com, create a project (any region near you), keep the default database.
2. Open **Connect**, copy the connection string. It looks like
   `postgresql://USER:PASSWORD@ep-xxxx.REGION.aws.neon.tech/DBNAME?sslmode=require`.
3. If the connection later fails with a `channel_binding` message, delete `&channel_binding=require` from the string.
Never put this string in a file you commit.

## 3. Load the data into Neon (from your laptop)
macOS / Linux:
```bash
export DATABASE_URL='postgresql://USER:PASSWORD@HOST/DBNAME?sslmode=require'
python scripts/generate_data.py --scale full --replace
python scripts/run_detection.py --no-eval
python scripts/validate_data.py
unset DATABASE_URL
```
Windows PowerShell: use `$env:DATABASE_URL='...'` and `Remove-Item Env:DATABASE_URL`.

Expect the same counts as local (5000 claims, 8000 edges) and `Unexpected failures: 0`. A shell variable overrides `.env`.
The script refuses to overwrite existing investigations unless you add `--wipe-investigations`.

## 4. Publish the code
The answer-key CSVs must be in the repo for the Evaluation page:
```bash
git add .gitignore data/ground_truth/*.csv
git commit -m "chore: commit synthetic answer key for the hosted Evaluation page"
git push origin main
git ls-files data/ground_truth      # should list 5 .csv files
```
They match the default-seed full dataset. If you regenerate with another seed or scale, regenerate **and** recommit them, or the
Evaluation page will report a mismatch.

## 5. Create the Streamlit app
1. Go to share.streamlit.io, sign in with GitHub, choose **Create app**.
2. Repository `dheerajreddysaddi/insurance-fraud-network-detection`, branch `main`, main file `app.py`.
3. Click **Advanced settings**: set **Python version 3.11** (the default is 3.12, which does not work with the pinned
   `numpy==1.26.4`), and paste into **Secrets**:
```toml
DATABASE_URL = "postgresql://USER:PASSWORD@HOST/DBNAME?sslmode=require"
APP_PASSCODE = "choose-a-strong-passcode"
REQUIRE_POSTGRES = "1"
```
4. Deploy. When it opens, the sidebar must say **Database: hosted PostgreSQL**. If it says SQLite or shows an error about
   `REQUIRE_POSTGRES`, the secrets were not picked up; fix them under the app's Settings > Secrets and reboot.

## 6. Share the URL
Copy the `https://<name>.streamlit.app` address from the browser. You can rename the subdomain in the app's Settings. Share the
URL and the passcode (separately) with your friend. Free apps can sleep after inactivity and wake on the next visit.

## 7. Updating
`git push origin main` redeploys automatically. Use **Reboot** in the app menu if it does not. Code updates never touch the database.

## 8. Persistence, backup, access control, reset
- **Persistence:** investigations, notes and events are rows in Neon, so they survive restarts and redeploys.
- **Backup** (needs PostgreSQL client tools): `pg_dump -Fc "$DATABASE_URL" > backup.dump`. Neon also offers restore features that
  vary by plan.
- **Access:** anyone with the URL can view the synthetic data. Writes (open, status, note, run detection) require the shared
  passcode. There is no reset or delete action in the UI. Rotate the passcode by editing the secret and rebooting.
- **Concurrent edits:** every change is one transaction; one investigation per subject is enforced by a UNIQUE constraint;
  status changes check the status the reviewer was looking at, so a stale tab gets "refresh and try again"; events are only ever
  inserted. Pages show other people's changes after a refresh or any click.
- **Safe reset of the demo data:** take a backup, then `python scripts/generate_data.py --scale full --replace`. It stops if
  investigations exist. Adding `--wipe-investigations` deliberately erases them.

## 9. Running locally instead
See the README Setup section; leave `DATABASE_URL` empty. Docker is optional.

## 10. Common failures
| Symptom | Cause / fix |
|---|---|
| Build fails on numpy or pyarrow | Python version is 3.12+. Redeploy with 3.11 in Advanced settings. |
| Sidebar says local SQLite on the hosted app | Secrets missing or mistyped; check `DATABASE_URL`. |
| "Database error (OperationalError)" | Wrong password/host, or paste of `channel_binding`; re-copy the string from Neon. |
| First load after idle is slow or fails once | Neon woke from suspend; reload. |
| Evaluation says labels do not match | Answer-key CSVs in the repo are from a different seed/scale than the database. |
| "database already contains data" while loading | Use `--replace`; investigations require `--wipe-investigations`. |
| Value too long for type character varying | Name or note field exceeded a column limit; names are capped at 60 characters. |

## 11. Acceptance checklist (record real results)
| Test | Result |
|---|---|
| App starts in local mode | |
| App connects to Neon (sidebar says hosted PostgreSQL) | |
| Same detection counts locally and on Neon (510 indicators, 268 flagged, 12 flagged networks) | |
| Create an investigation and change its status online | |
| It is still there after Reboot app | |
| Second browser (private window) sees the same data | |
| Change in one browser visible in the other after refresh | |
| Re-running `generate_data.py --replace` is refused while investigations exist | |
| Clean checkout installs from README only (ask your friend, or use a fresh folder) | |
| Friend opens the URL on their own laptop without installing anything | |
