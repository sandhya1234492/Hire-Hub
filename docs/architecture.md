# Architecture

HireHub is organized as a Flask application factory with separate web and JSON API blueprints. The request flow is:

```text
Web/API blueprint -> service -> repository -> PyMongo collection
```

`app/__init__.py` configures the application, sessions, Mongo client, blueprints, and common HTTP errors. Routes translate HTTP requests into service calls and render templates or JSON. Services enforce domain rules such as registration validation, job ownership, application transitions, matching, file validation, notifications, and audit events. Repositories encapsulate reusable document operations. Domain classes in `app/models/entities.py` represent users and hiring entities.

Configuration is read from environment variables and `.env`; do not commit `.env`. MongoDB is accessed through the application-scoped `get_database()` helper. Set `COOKIE_SECURE=true` behind HTTPS. In production, configure TLS, a strong secret, a least-privilege MongoDB user, and an application server.

Resume files are assigned random server-generated names and stored separately from their metadata. Access is restricted to the candidate, recruiters, and admins. Candidate/recruiter authorization is checked server-side, including ownership of jobs and applications.
