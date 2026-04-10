# Django App

Local run instructions for this Django project.

## Prerequisites

- Python 3.10+ (tested with Python 3.12)
- `pip`
- A terminal in this project root (same folder as `manage.py`)

## 1. Open project folder

```bash
cd .../django_projects/mysite
```

## 2. Create and activate a virtual environment

For Linux/WSL/macOS:

```bash
python3 -m venv .venv-linux
source .venv-linux/bin/activate
```

For Windows PowerShell:

```powershell
py -m venv .venv-win
.\.venv-win\Scripts\Activate.ps1
```

## 3. Install dependencies

```bash
python -m pip install --upgrade pip
pip install -r requirements.txt
```

## 4. Configure settings for local development

Edit `mysite/settings.py` and set:

- `DEBUG = True`
- `ALLOWED_HOSTS = ['127.0.0.1', 'localhost']`


## 5. Apply database migrations

```bash
python manage.py migrate
```

## 6. (Optional) Create an admin user

```bash
python manage.py createsuperuser
```

## 7. Start the development server

```bash
python manage.py runserver 127.0.0.1:8000 --noreload
```

Open in browser:

- http://127.0.0.1:8000/
- Admin: http://127.0.0.1:8000/admin/

## Notes

- Local development uses SQLite by default (`db.sqlite3`).
- Do not set `DJANGO_USE_PYTHONANYWHERE_DB=1` unless you intend to use MySQL on PythonAnywhere.
- GitHub OAuth settings are read from `mysite/github_settings.py`; social login is optional for local app startup.
- Images and thumbnails on local need media serving enabled. In this project, media URLs are served in debug mode, so keep `DJANGO_DEBUG=1` locally. For production, set `DJANGO_DEBUG=0` and serve media with your web server.
- `ALLOWED_HOSTS` is configurable through `DJANGO_ALLOWED_HOSTS` (example production value: `ikosmaz.pythonanywhere.com`).

## Quick troubleshooting

- `ModuleNotFoundError: No module named 'django'`
  - Activate the venv and run `pip install -r requirements.txt`.
- `DisallowedHost`
  - Re-check `ALLOWED_HOSTS` in `mysite/settings.py`.
- MySQL connection errors
  - Ensure `DJANGO_USE_PYTHONANYWHERE_DB` is not set for local use.
