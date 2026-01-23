# Dashboard Development Notes

## Running the Flask App

The dashboard runs on port 8082. Start it from the dashboard directory:

```bash
cd /home/david/projects/aegis/dashboard
flask --app app run --port 8082
```

For auto-reload during development (picks up Python and template changes automatically):

```bash
flask --app app run --port 8082 --debug
```

## Restarting After Code Changes

If running without `--debug`, you must restart the app to pick up changes to:
- Python files (routes, config, etc.)
- Templates (though sometimes cached)

### Find and kill the running process:

```bash
# Find what's using port 8082
lsof -i :8082

# Kill it (replace PID with actual number)
kill <PID>

# Or one-liner:
kill $(lsof -t -i :8082)
```

### Then restart:

```bash
cd /home/david/projects/aegis/dashboard
flask --app app run --port 8082
```

## Production Deployment

For production, the app runs via systemd:

```bash
sudo systemctl status aegis
sudo systemctl restart aegis
sudo journalctl -u aegis -f  # View logs
```

## Key Files

- `app.py` - Flask app factory and blueprint registration
- `config.py` - Configuration settings
- `routes/` - Route blueprints:
  - `hai.py` - HAI Detection routes (`/hai-detection/`)
  - `au_ar.py` - NHSN Reporting routes (`/nhsn-reporting/`)
  - `asp.py` - ASP Alerts routes (`/asp-alerts/`)
- `templates/` - Jinja2 templates
- `static/` - CSS, JS, images
