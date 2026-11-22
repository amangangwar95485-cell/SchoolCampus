# SmartCampus — Flask + Gunicorn

A Python-based campus management portal built with Flask, SQLite, Jinja templates and Gunicorn.

## Features

- Role-based login (admin, faculty and student)
- Student registration and student directory
- Attendance marking and student attendance view
- Campus notices with **admin-only deletion**
- Student complaints and admin status updates
- Department timetable
- Student directory CSV export

## Run locally

Python 3.10 or newer is recommended.

```bash
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS/Linux:
source .venv/bin/activate
pip install -r requirements.txt
```

Set a local secret key before starting the app.

Windows PowerShell:
```powershell
$env:SECRET_KEY = "replace-with-a-long-random-secret"
python app.py
```

macOS/Linux:
```bash
export SECRET_KEY="replace-with-a-long-random-secret"
python app.py
```

Open http://127.0.0.1:8000.

## Deploy on Render

1. Push the contents of this folder to a GitHub repository (do not upload `.git`, `.env`, or `smartcampus.db`).
2. In Render, create **New + → Web Service** and connect the repository.
3. If the files are in the repository root, leave Root Directory blank.
4. Build command: `pip install -r requirements.txt`
5. Start command: `gunicorn --workers 2 --bind 0.0.0.0:$PORT app:app`
6. Add an environment variable named `SECRET_KEY` with a long random value.
7. Deploy.

### Database persistence on Render

The app creates `smartcampus.db` automatically. Render's ordinary service filesystem is ephemeral, so SQLite data may be lost on a redeploy or restart. For persistent production data, attach a Render persistent disk and configure the app to store the database on that disk, or migrate to PostgreSQL. Do not rely on the included demo database for production; no database file is included in this source archive.

## Demo accounts

On a fresh database, the app seeds these local demonstration accounts:

- Admin: `admin@smartcampus.local` / `Admin@123`
- Faculty: `faculty@smartcampus.local` / `Faculty@123`
- Student: `student@smartcampus.local` / `Student@123`

Change demo passwords and use a secure `SECRET_KEY` before exposing a deployment publicly. Demo accounts are for coursework/testing only.

## Notice deletion

Only an administrator sees the **Delete notice** button. Deletion uses a POST request, asks for confirmation in the browser, and removes only the selected notice ID.
