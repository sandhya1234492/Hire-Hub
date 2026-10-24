# API

All API endpoints are prefixed with `/api`. JSON success responses use `{ "success": true, "message": "...", "data": ... }`; errors use `{ "success": false, "message": "...", "error_code": "..." }`. Authentication uses the same secure Flask session cookie as the web interface.

| Method | Endpoint | Access |
|---|---|---|
| POST | `/auth/register` | Public (candidate/recruiter) |
| POST | `/auth/login` | Public |
| POST | `/auth/logout` | Authenticated |
| GET | `/auth/me` | Authenticated |
| GET | `/jobs` | Public |
| GET | `/jobs/<id>` | Public |
| POST | `/jobs` | Recruiter |
| PUT | `/jobs/<id>` | Owning recruiter |
| DELETE | `/jobs/<id>` | Owning recruiter (closes job) |
| GET/PUT | `/candidates/<id>` | Candidate owner, recruiter, or admin for GET; owner for PUT |
| POST | `/jobs/<id>/apply` | Candidate |
| POST/DELETE | `/jobs/<id>/save` | Candidate |
| GET | `/applications` | Authenticated; scoped by role |
| GET | `/applications/<id>` | Owner, job recruiter, or admin |
| PUT | `/applications/<id>/status` | Owning recruiter |
| POST | `/applications/<id>/withdraw` | Candidate owner |
| POST/GET | `/interviews` | Recruiter create; authenticated list |
| PUT | `/interviews/<id>` | Owning recruiter |
| POST | `/resumes` | Candidate |
| GET/DELETE | `/resumes/<id>` | Authorized resume reader / candidate owner |
| GET | `/analytics/<candidate\|recruiter\|admin>` | Corresponding role or admin |
| GET | `/notifications` | Authenticated |
| POST | `/notifications/<id>/read` | Notification owner |

Job search supports combined `keyword`, `skill`, `location`, `min_salary`, `max_salary`, `experience`, `work_mode`, `employment_type`, `company`, `page`, and `per_page` parameters. For example:

```text
GET /api/jobs?skill=python&location=bengaluru&work_mode=HYBRID&page=1
```
