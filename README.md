# Campus Activity Registration, Lottery & Check-in System

A campus activity platform covering the full loop **publish - register - random lottery - waitlist promotion - QR check-in - statistics & Excel export**, with a fair and reproducible (seed-auditable) lottery.

- **Backend**: FastAPI + SQLAlchemy 2.0 + SQLite (switchable to MySQL)
- **Frontend**: vanilla HTML / CSS / JS, no build step
- **Tests**: 78 pytest cases on in-memory SQLite

The implementation follows the development document; the full document set lives in [`docs/`](docs/README.md). This README corresponds to the deployment chapter of that document.

## Features

- Three roles (student, organizer, admin) with JWT authentication
- Activity CRUD, publish, cancel, quota and sign-up deadline
- Registration with optional waitlist; cancel and re-register; winner withdrawal
- Idempotent, reproducible lottery (atomic conditional UPDATE + seeded shuffle)
- Automatic lottery scheduler (APScheduler) with a read-time fallback
- Waitlist auto-promotion in the same transaction as withdrawal or quota increase
- QR check-in (PNG, `Cache-Control: no-store`), duplicate rejection with first check-in time, manual check-in by student ID
- Statistics (six counts, three ratios) and Excel export (registration list / winners list)
- 78 automated tests; performance target: lottery over 1000 registrations under 1 s (measured 48 ms)

## Tech stack

| Layer | Choice |
| --- | --- |
| Backend | FastAPI 0.111.0 |
| ORM | SQLAlchemy 2.0.30 |
| Database | SQLite (`app.db`); MySQL 8 by changing `DATABASE_URL` only |
| Frontend | Vanilla HTML + `fetch`, no build tooling |
| Auth | PyJWT HS256 + passlib[bcrypt] |
| QR code | qrcode + pillow |
| Excel | openpyxl |
| Scheduler | APScheduler |

## Requirements

- Windows 10 / 11 (run the equivalent commands on other platforms)
- Python 3.10 / 3.11, with Python added to PATH
- Chrome / Edge

## Quick start

### Option 1 - one-click script (recommended)

1. Get the project and open the folder.
2. Double-click `run.bat` (demo mode: single process, no `--reload`, auto lottery enabled).
   For development use `run.bat dev` (`--reload`; the script disables the auto lottery to avoid a second scheduler instance).
3. Open <http://localhost:8000>.

The script creates `.venv`, installs dependencies, generates `.env` with a random `SECRET_KEY`, runs `python seed.py` and starts the server.

### Option 2 - manual

```bat
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
python -c "import secrets;print(secrets.token_hex(32))"   :: put the value into SECRET_KEY
python seed.py
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

## Default accounts (created by `seed.py`)

| Role | Username | Password | Notes |
| --- | --- | --- | --- |
| Admin | `admin` | `admin123` | from `.env`; can manage user roles and status |
| Organizer | `org1`, `org2` | `123456` | demo activities |
| Student | `stu001` .. `stu020` | `123456` | 20 registrations per activity |

Demo activities close 2 minutes after `seed.py` runs; the scheduler then draws within 30 seconds.

## Pages

| Page | URL | Role |
| --- | --- | --- |
| Login / register | `/login.html`, `/register.html` | public |
| Activity list | `/index.html` | all |
| Activity detail and sign-up | `/activity_detail.html?id=<id>` | student |
| My registrations (QR code) | `/my_registrations.html` | student |
| Create activity | `/organizer.html` | organizer / admin |
| Activity management | `/activity_manage.html?id=<id>` | organizer / admin |
| Check-in desk | `/checkin.html` | organizer / admin |
| User management | `/admin.html` | admin |

API docs: <http://localhost:8000/api/docs> (Swagger) and <http://localhost:8000/redoc>.

## Tests

```bat
.venv\Scripts\activate
python -m pytest tests\
```

78 cases run against in-memory SQLite (`StaticPool`) and never touch `app.db`.

## Documentation

The full life-cycle document set is indexed in [`docs/README.md`](docs/README.md): 15 documents, provided as Markdown only (Word versions are generated on demand). Document bodies are written in Chinese; [`docs/README.zh-CN.md`](docs/README.zh-CN.md) is the Chinese index.

Generate Word versions when needed (the generated .docx files are gitignored):

```bat
python scripts\md_to_docx.py
python scripts\verify_docx.py
```

## Repository layout

```
app/                # backend (config, database, models, routers, services, scheduler)
static/             # frontend pages (vanilla HTML/CSS/JS)
tests/              # pytest cases
docs/               # life-cycle document set (Markdown only)
scripts/            # documentation build and check scripts
seed.py             # idempotent demo data
init_db.py          # standalone table creation
run.bat             # one-click Windows launcher (demo / dev)
.env.example        # configuration template (.env is not committed)
```

## Configuration notes

- `SECRET_KEY` must be a random string of at least 16 characters; startup fails otherwise.
- `PUBLIC_BASE_URL` must be reachable from the phone for QR check-in (use the LAN IP, e.g. `http://192.168.1.20:8000`).
- Run a **single process, single worker** and never use `--reload` for demo or acceptance runs: multiple scheduler instances would draw twice.
- Dependencies are pinned; `passlib` 1.7.4 and `bcrypt` 4.1.3 must be upgraded together.

## FAQ

- **Port already in use** - run `uvicorn app.main:app --port 8001` and update `PUBLIC_BASE_URL` accordingly.
- **QR code does not open on the phone** - `PUBLIC_BASE_URL` is still `http://localhost:8000`; set the LAN IP and restart.
- **`database is locked`** - WAL, `timeout=30` and a retry decorator are enabled; make sure only one process writes `app.db`.
- **Switch to MySQL** - change `DATABASE_URL` only, then `pip install pymysql cryptography`, `python init_db.py`, `python seed.py`.
- **Reset demo data** - stop the server, delete `app.db*`, then run `python seed.py`.

## License

No license file is included. Add a `LICENSE` before publishing if you intend to open-source this project.
