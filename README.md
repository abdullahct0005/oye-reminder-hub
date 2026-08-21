
# OYE Course Reminder Hub — Shared Web Dashboard

## What this version does
- One web dashboard for all Regional Trainers.
- No Python/CMD installation needed for end users after deployment.
- Works with trainers using normal WhatsApp Messenger or WhatsApp Business.
- Trainer selects their own name and sees only their OECs from the uploaded report.
- Course-specific pending/completed detection.
- Personalised reminder messages.
- WhatsApp chat links with pre-filled messages.
- First, second and urgent reminder templates.
- Session-based campaign progress.

## Recommended deployment
Deploy this repository on Streamlit Community Cloud.

### Prepare GitHub
1. Create a new GitHub repository.
2. Upload:
   - app.py
   - requirements.txt
3. Commit the files.

### Deploy
1. Open Streamlit Community Cloud.
2. Sign in with GitHub.
3. Select the repository.
4. Set the main file to `app.py`.
5. Deploy.

Your team will then receive one web URL.

## Important
This first shared version does not permanently store OYE reports or campaign history. That is intentional so the app can be deployed quickly.

For the next enterprise version, add:
- Trainer login/PIN
- Central admin report upload
- Persistent campaign history
- Scheduled reminders
- Per-trainer dashboard
- Cloud database (Supabase/Firebase)
