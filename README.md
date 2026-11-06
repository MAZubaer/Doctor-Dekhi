# Doctor Dekhi

Backend for a hospital serial and queue system for public hospitals in
Bangladesh. Patients find a doctor, book a serial and track their place in the
queue.

Built with FastAPI, SQLAlchemy 2.0, PostgreSQL (Neon) and psycopg 3.

## Setup

Requires Python 3.11 or newer. On Windows PowerShell:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
```

On macOS or Linux, activate with `source .venv/bin/activate` and copy with
`cp .env.example .env`.

Then edit `.env` and set `DATABASE_URL` and `JWT_SECRET`. The database URL must
start with `postgresql+psycopg://`.

## Choosing a database

`APP_ENV` selects the database for both the app and `seed.py`:

| `APP_ENV`        | Target | URL used           |
| ---------------- | ------ | ------------------ |
| `prod` (default) | main   | `DATABASE_URL`     |
| `dev`            | dev    | `DEV_DATABASE_URL` |

Set `APP_ENV=dev` in `.env` to make dev the default on your machine, or set it
for one PowerShell session:

```powershell
$env:APP_ENV = "dev"
```

With `APP_ENV=dev`, startup fails if `DEV_DATABASE_URL` is missing or matches
`DATABASE_URL`. It never falls back to the main database. The app and `seed.py`
both print the target, for example `dev (pooled host)`, and never the URL.

## Seed the database

```powershell
python seed.py --dev
```

**This drops every table in the target database**, recreates them and inserts
demo data. `--dev` does the same as `APP_ENV=dev`. Without it, and without
`APP_ENV=dev`, the target is the main database.

Schedules are created for today and tomorrow in Bangladesh time, 09:00 to 13:00,
so re-run the seed on the day of a demo. Today's schedules stop accepting
bookings at 13:00, so use tomorrow's date after that.

## Demo logins

All seeded staff accounts use the password `Demo@1234`. These are demo accounts
only.

| Role           | Phone       | Hospital                            |
| -------------- | ----------- | ----------------------------------- |
| super_admin    | 01700000001 | All hospitals                       |
| hospital_admin | 01700000011 | Dhaka Medical College Hospital      |
| staff          | 01700000012 | Dhaka Medical College Hospital      |
| hospital_admin | 01800000011 | Chattogram Medical College Hospital |
| staff          | 01800000012 | Chattogram Medical College Hospital |

## Run

```powershell
uvicorn app.main:app --reload
```

- Swagger UI: <http://127.0.0.1:8000/docs>
- Health check: <http://127.0.0.1:8000/health>

## Endpoints

| Method | Path                                 | Purpose                             |
| ------ | ------------------------------------ | ----------------------------------- |
| GET    | `/health`                            | Check the API and database          |
| GET    | `/hospitals`                         | List hospitals                      |
| GET    | `/hospitals/{hospital_id}/departments` | List a hospital's departments     |
| GET    | `/doctors/available`                 | List bookable doctors and schedules |
| POST   | `/serials`                           | Book a serial                       |
| GET    | `/serials/{serial_id}/status`        | Check queue status                  |

Every error uses one JSON shape:

```json
{
  "error": "SCHEDULE_FULL",
  "message": "No serials left for this doctor on this schedule.",
  "details": null
}
```

## Project layout

```text
app/
  main.py       FastAPI app and health check
  config.py     Settings loaded from .env
  database.py   Engine, session factory and get_db dependency
  models.py     SQLAlchemy models and enums
  schemas/      Pydantic schemas
  routers/      API routes
  services/     Business logic
  core/         Errors, Bangladesh time and phone helpers
seed.py         Resets the database and inserts demo data
tests/          Test suite
```
