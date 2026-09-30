# Development setup

The project requires Python 3.11+.

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
flask --app run.py run --debug
```

The development database is created in `instance/food_ordering.sqlite3`. The repository includes the migration environment; apply its revisions with:

```powershell
flask --app run.py db upgrade
```
