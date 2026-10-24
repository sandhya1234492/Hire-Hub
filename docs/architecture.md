# Architecture

HireHub is organized as a Flask application factory with separate web and JSON API blueprints. The request flow is:

```text
Web/API blueprint -> service -> repository -> PyMongo collection
```

`app/__init__.py` configures the application, sessions, Mongo client, blueprints, and common HTTP errors. Routes translate HTTP requests into service calls and render templates or JSON. Services enforce domain rules such as registration validation, job ownership, application transitions, interview lifecycle, company profile verification resets, matching, report filters, file validation, notifications, and audit events. Repositories encapsulate reusable document operations. Domain classes in `app/models/entities.py` represent users and hiring entities.

Admin provisioning is intentionally out-of-band: `flask --app run.py create-admin` reads temporary `HIREHUB_ADMIN_NAME`, `HIREHUB_ADMIN_EMAIL`, and `HIREHUB_ADMIN_PASSWORD` environment variables, hashes the password, and refuses duplicate emails. Admin management web routes and JSON APIs require the `ADMIN` role. Candidate and recruiter registrations cannot request that role.

Configuration is read from environment variables and `.env`; do not commit `.env`. MongoDB is accessed through the application-scoped `get_database()` helper. Set `COOKIE_SECURE=true` behind HTTPS. In production, configure TLS, a strong secret, a least-privilege MongoDB user, and an application server.

Resume files are assigned random server-generated names and stored separately from their metadata. Access is restricted to the candidate, admins, and recruiters who have a candidate application for one of their jobs. Candidate/recruiter authorization is checked server-side, including ownership of jobs and applications.

Recruiters can edit only their associated company; changes to material company details clear its verified state pending admin review. Admin reports use MongoDB data and enforce role authorization before displaying or exporting records.
