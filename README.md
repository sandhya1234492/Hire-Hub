# HireHub

HireHub is a Flask and MongoDB recruitment portal with candidate, recruiter, and admin roles. It includes registration and login, job discovery, candidate applications, recruiter job and applicant management, a JSON API, interview scheduling, resume uploads, matching, and a responsive Bootstrap interface.

## Requirements

- Python 3.12 or newer
- MongoDB 6.0 or newer

## Run locally

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
# Create or edit .env with MONGO_URI, MONGO_DATABASE, SECRET_KEY, UPLOAD_FOLDER,
# MAX_CONTENT_LENGTH, and COOKIE_SECURE. Keep .env private.
python run.py
```

The development server runs at `http://127.0.0.1:5000`. MongoDB is accessed lazily; database-backed pages require a reachable server at `MONGO_URI`.

Generate a private Flask secret with `python -c "import secrets; print(secrets.token_hex(32))"` and put the output in `.env` as `SECRET_KEY=<generated-value>`. For a local MongoDB server, set `MONGO_URI=mongodb://localhost:27017` and `MONGO_DATABASE=hirehub`.

## Fictional demo data

With MongoDB configured in `.env`, create the search and relationship indexes and seed the fictional demo records:

```powershell
python scripts\create_indexes.py
python scripts\seed_data.py
python run.py
```

The seeder is idempotent. It creates 20 candidates, 10 recruiters, 5 demo companies, 30 jobs, 50 applications, 15 interviews, 20 downloadable fictional resume files and metadata, demo notifications, and one demo admin. Rerunning updates only documents explicitly marked as demo data. It does not delete or reset existing records; if one of the reserved demo emails or company names conflicts with a non-demo record, the seeder stops before making changes.

**Development-only demo credentials** (all fictional accounts use hashed passwords):

| Role | Email | Password |
|---|---|---|
| Candidate | `candidate01@demo.hirehub.test` | `HireHubDemo2026!` |
| Recruiter | `recruiter01@demo.hirehub.test` | `HireHubDemo2026!` |
| Admin | `admin@demo.hirehub.test` | `HireHubAdmin2026!` |

Log in at `http://127.0.0.1:5000/login`. These fixed demo credentials are for local development only. Never deploy demo accounts or these passwords to production; use the secure `create-admin` CLI flow below to provision a production administrator.

For a production deployment, set `FLASK_ENV=production`, use HTTPS, provide a strong secret and a MongoDB user with least-privilege access, and serve Flask through a production WSGI server.

## Roles and first admin

Candidate and recruiter accounts can be created at `/register`. Admin is not offered on public registration and the registration service rejects the `ADMIN` role. Create the first admin with the Flask CLI after configuring `.env` and starting MongoDB. These environment variables are used only by the creation command:

```powershell
$env:HIREHUB_ADMIN_NAME = "HireHub Admin"
$env:HIREHUB_ADMIN_EMAIL = "admin@example.com"
$securePassword = Read-Host "Admin password (12 characters minimum)" -AsSecureString
$env:HIREHUB_ADMIN_PASSWORD = [System.Net.NetworkCredential]::new("", $securePassword).Password
python -m flask --app run.py create-admin
Remove-Item Env:HIREHUB_ADMIN_NAME, Env:HIREHUB_ADMIN_EMAIL, Env:HIREHUB_ADMIN_PASSWORD
```

The CLI validates the credentials, refuses to overwrite an existing email, hashes the password before storing it, and writes an audit event. Admins sign in at `/login` using the same login page as other users and are sent to `/admin/dashboard`. Admin accounts are not created or updated by public registration. Keep the admin password out of source control and clear its environment variable after use.

## Features

- Session-based authentication, role authorization, and hashed passwords
- Job search with combined keyword, skill, location, salary, experience, work-mode, employment-type, and company filters
- Candidate profiles (including education and experience), saved jobs, applications, matching scores, and application tracking
- Recruiter company profiles, job publishing/editing/closing, applicant status management, and interview lifecycle controls
- Protected resume upload/download (PDF, DOC, DOCX), interview scheduling, and notifications
- Candidate job recommendations, paginated listings, JSON API under `/api`, administrator dashboard, audit logging, MongoDB indexes, and seed data
- Admin analytics and filterable CSV reports for applications, recruitment outcomes, jobs, candidates, and skills
- Admin-only user management, company verification, job moderation, application monitoring, analytics, CSV reports, and audit logs
- Responsive Bootstrap-based templates

## Tests

```powershell
python -m pip install -r requirements-dev.txt
pytest
```

Tests use `mongomock`; they do not need a running MongoDB instance.

## Documentation

- [Architecture](docs/architecture.md)
- [API](docs/api.md)
- [Database](docs/database.md)
