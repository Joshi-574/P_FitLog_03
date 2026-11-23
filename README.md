# FitLog Dashboard

FitLog is a Streamlit workout tracker with local accounts, private workout history, personal CSV reports, an authenticated local API, and an optional Anthropic Claude coach.

## Start the dashboard

Open PowerShell in this folder and run:

```powershell
python -m pip install -r requirements.txt
python -m streamlit run "dashboard (1).py"
```

Create an account from the **Sign up** tab the first time you open it. The first account becomes the administrator; accounts created afterward are regular users. Administrators can view account names, roles, and workout counts in **Admin Panel**, and change another account's role. The panel does not expose workout entries. Sign in to see your account's workouts. Passwords are stored as salted PBKDF2 hashes. Existing single-user workouts are assigned to the first account that signs up.

## Log workouts and download reports

Use **Log a Workout** to enter an activity. The dashboard stores it in SQLite under the signed-in account. The sidebar's **My Data Report** downloads only that account's workouts as CSV. The Workout History section also has filters and a CSV download.

## Back up and restore data

Open **Backup & SQLite** in the sidebar. **Export full JSON snapshot** creates a backup of the signed-in account's workouts. **Export SQLite SQL dump** downloads SQL statements that can be opened with SQLite tools. To restore, upload a FitLog JSON snapshot and select **Restore JSON backup to my account**. Existing matching workouts are skipped to avoid duplicates. CSV download is available under **My Data Report**.

## Enable the Claude AI Coach

The optional coach uses Anthropic's Messages API. Create an API key in the [Anthropic Console](https://console.anthropic.com/), open **Claude AI Coach** in the sidebar, and paste the key into the masked **Anthropic API key** field. The key stays in the active Streamlit session and is not saved to the project files. Do not share it. Claude Coach is limited to FitLog/FitCircle project questions and questions about the signed-in account's recorded workout report. A local scope check declines ordinary general questions before they are sent to Anthropic; the API prompt also instructs Claude to refuse unrelated or mixed-topic requests.

For repeat local use, copy `.streamlit/secrets.toml.example` to `.streamlit/secrets.toml` and set `ANTHROPIC_API_KEY = "your-key"`. That file is ignored by Git; never commit it.

## Local API

Start it in a second PowerShell window:

```powershell
python api.py
```

The API listens on `http://127.0.0.1:8000` and requires HTTP Basic authentication using a FitLog username and password.

- `GET /api/health` checks whether the API is running.
- `GET /api/workouts` returns the authenticated account's workouts.
- `POST /api/workouts` adds a workout to the authenticated account. Example JSON:

  ```json
  {"date":"2026-11-03","workout":"Running","duration":30,"calories":200}
  ```

## Run the tests

```powershell
python -m pytest -q
```

Tests use temporary SQLite databases and do not target the FitLog user database. The dashboard also has a **Testing & Quality** panel that reports passed/failed tests, elapsed time, and output.

## FitCircle

After signing in, choose a FitCircle page from the sidebar. Users can search usernames or FitLog IDs, send/accept/reject/cancel requests, remove friends, and invite new users with a code. A code never creates a friendship automatically. Discovery, leaderboard participation, leaderboard visibility, and each shared comparison metric are opt-in; progress comparison requires an accepted friendship.

Challenges use recorded FitLog workout count or duration. Challenge creators can invite accepted friends. Challenge completion earns a stored badge. FitLog does not record steps or sensor data, so step challenges, daily step comparisons, and nearby discovery are unavailable. The local SQLite database is for a single shared computer and does not synchronize accounts between devices; multi-device social use needs a hosted shared backend.
## Import smart device steps

Open **Device Data** in the sidebar and upload a daily activity CSV exported from Fitbit, Garmin, Apple Health, Google Health Connect, or another source. Choose its date and steps columns, then import. The project stores one daily total per account and source; re-importing a date updates it instead of duplicating it. Actual imported readings can be used in step challenges. Friends see weekly totals only after the account owner enables step sharing under **Privacy & Invitations**.

This is a user-initiated file import, not background or direct device synchronization. The Streamlit app cannot request native Apple Health or Android Health Connect permissions; direct sync requires a provider-specific mobile client or OAuth integration and its credentials. Local SQLite remains on this computer.