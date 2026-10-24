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
Copy-Item .env.example .env
# Set SECRET_KEY and MONGO_URI in .env
python run.py
```

The development server runs at `http://127.0.0.1:5000`. MongoDB is accessed lazily; database-backed pages require a reachable server at `MONGO_URI`.

For a production deployment, set `FLASK_ENV=production`, use HTTPS, provide a strong secret and a MongoDB user with least-privilege access, and serve Flask through a production WSGI server.

## Roles and first admin

Candidate and recruiter accounts can be created at `/register`. Admin accounts are intentionally not publicly registrable. Create an admin using the provided script:

```powershell
python scripts\create_admin.py --name "HireHub Admin" --email admin@example.com
```

The script prompts for a password and hashes it before storing it.

## Features

- Session-based authentication, role authorization, and hashed passwords
- Job search with combined keyword, skill, location, salary, experience, work-mode, employment-type, and company filters
- Candidate profiles, saved jobs, applications, matching scores, and application tracking
- Recruiter company association, job publishing/editing/closing, and applicant status management
- Protected resume upload/download (PDF, DOC, DOCX), interview scheduling, and notifications
- JSON API under `/api`, administrator dashboard, audit logging, MongoDB indexes, seed data, and reports as CSV
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
