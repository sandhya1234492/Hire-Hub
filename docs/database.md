# Database

HireHub uses the database named by `MONGO_DATABASE`. Collections:

| Collection | Purpose |
|---|---|
| `users` | Authentication identity, role, profile fields, and company association |
| `candidates` | Candidate-side profile metadata |
| `recruiters` | Recruiter-side company association |
| `companies` | Company profile and verification state |
| `jobs` | Published job details, search attributes, status, and owner |
| `applications` | Candidate/job relationship, status history fields, and recruiter notes |
| `interviews` | Scheduled interview details and feedback |
| `resumes` | Candidate-owned resume metadata; files remain on disk |
| `notifications` | User notifications and read state |
| `audit_logs` | Security-relevant action, resource, timestamp, and non-secret metadata |

Run `python scripts/create_indexes.py` to create unique email, application, and resume indexes, plus job search and notification indexes. The application service prevents duplicate applications before insertion; the unique compound index also enforces this invariant in the database.

Run `python scripts/seed_data.py` only against an empty database. It inserts fictional records and random unusable password hashes, so seeded accounts cannot be used to log in.
