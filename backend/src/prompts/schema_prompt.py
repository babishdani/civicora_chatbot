SCHEMA = """
Table: grievances

Columns:
id
grievance_code
title
category_code
sub_category
description
citizen_name
citizen_mobile
citizen_email
block_code
panchayat_code
village_code
ward_street
landmark
manual_override
status_code
work_stage_code
work_progress
priority_score
priority_rank
priority_label
priority_population
priority_safety
priority_political
priority_disruption
escalation_level
escalated_at
attachment_url
attachment_key
attachment_name
resolution_proof_url
resolution_proof_key
resolution_proof_name
feedback_submitted_at
citizen_email_alert_status
citizen_email_alert_message
status_reason
created_at
updated_at
voice_note_url
voice_note_key
voice_note_name



Table: activities

Columns:
id
activity_code
title
category
activity_date
location
description
status
created_by
created_at
updated_at


Table: job_fairs

Columns:
id
job_code
title
assumed_date
status_code
venue
partners
candidates
placements
created_by
created_at
updated_at


Table: job_fair_statuses

Columns:
id
code
label
sort_order
is_active
created_at
updated_at


Table: users

Columns:
id
role
category_id
name
is_active
last_login_at
official_id
password_hash
mobile_number
email
created_at
updated_at
login_password


RELATIONSHIP:
- users.id identifies the authenticated account.
- users.mobile_number corresponds to grievances.citizen_mobile.
- This mapping must be verified against actual database records.
- Citizens may access only their own grievance records.
- Admin and Commander permissions must be enforced by the backend.


SQL RULES:
- Generate SELECT queries only.
- Never generate INSERT, UPDATE, DELETE, DROP, ALTER,
  TRUNCATE, or other data-modifying statements.
- Never use SELECT *.
- Use only the tables and columns listed in this schema.
- Use explicit column names.
- Do not generate queries that retrieve passwords, password hashes,
  login_password, OTPs, OTP hashes, refresh tokens, access tokens,
  or secret keys.
- Do not assume a status code exists unless it is in the database.
- Use parameterized queries wherever user input is involved.
- Never bypass backend authorization or ownership filters.
"""