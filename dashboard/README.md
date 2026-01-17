# ASP Alerts Dashboard

Web-based alert management dashboard for the ASP Alerts system. Provides a unified interface for viewing, acknowledging, and resolving antimicrobial stewardship alerts.

> **Disclaimer:** All patient data displayed is **simulated**. No actual patient data is available through this dashboard.

## Live Demo

**URL:** [https://alerts.asp-ai-agent.com:8444](https://alerts.asp-ai-agent.com:8444)

## Features

### Alert Management
- **Active Alerts** - View pending, sent, acknowledged, and snoozed alerts
- **History** - Browse resolved alerts with resolution details
- **Alert Detail** - Full patient and clinical information with action buttons

### Actions
- **Acknowledge** - Mark alert as seen (remains in active list)
- **Snooze** - Temporarily suppress for 4 hours
- **Resolve** - Close alert with resolution reason and notes

### Resolution Tracking
Track how alerts were handled:
- Acknowledged (no action needed)
- Messaged Team
- Discussed with Team
- Therapy Changed
- Therapy Stopped
- Patient Discharged
- Other

### Reports & Analytics
- Alert volume over time
- Average alerts per day
- Resolution rate
- Time to acknowledge/resolve
- Resolution reason breakdown with percentages
- Alerts by severity and status
- Alerts by day of week

### Filtering
- Filter by alert type (Bacteremia, Antimicrobial Usage)
- Filter by severity (Critical, Warning, Info)
- Filter by resolution reason
- Search by patient MRN

### Additional Features
- **Auto-refresh** - Active alerts page refreshes every 30 seconds
- **Relative timestamps** - "2 hours ago" format for easy scanning
- **Audit trail** - Full history of actions on each alert
- **Help page** - Built-in demo workflow guide
- **CCHMC branding** - Cincinnati Children's color scheme

## Quick Start

### Development

```bash
cd asp-alerts/dashboard

# Install dependencies
pip install -r requirements.txt

# Copy and configure environment
cp .env.template .env
# Edit .env with your settings

# Run development server
flask run

# Visit http://localhost:5000
```

### Production Deployment

The dashboard is deployed at `alerts.asp-ai-agent.com:8444` using:
- **Gunicorn** - WSGI server
- **nginx** - Reverse proxy with SSL
- **systemd** - Service management
- **Let's Encrypt** - SSL certificates

See [deploy/](deploy/) for configuration files.

#### Deployment Commands

```bash
# Copy static files to web root
sudo cp static/style.css /var/www/asp-alerts/static/

# Restart the service
sudo systemctl restart asp-alerts

# Check status
sudo systemctl status asp-alerts

# View logs
sudo journalctl -u asp-alerts -f
```

## Configuration

Copy `.env.template` to `.env` and configure:

```bash
# Flask settings
FLASK_ENV=production
FLASK_DEBUG=false
FLASK_SECRET_KEY=your-secret-key

# Server
PORT=8082

# Dashboard URL (for Teams button callbacks)
DASHBOARD_BASE_URL=https://alerts.asp-ai-agent.com:8444

# Alert database (shared with monitors)
ALERT_DB_PATH=~/.asp-alerts/alerts.db

# App display name
APP_NAME=ASP Alerts
```

## Architecture

```
dashboard/
├── app.py                 # Flask application factory
├── config.py              # Configuration management
├── routes/
│   ├── views.py           # HTML page routes
│   └── api.py             # API endpoints for Teams callbacks
├── templates/
│   ├── base.html          # Base layout with navigation
│   ├── alerts_active.html # Active alerts list
│   ├── alerts_history.html# Historical alerts
│   ├── alert_detail.html  # Single alert view
│   ├── reports.html       # Analytics dashboard
│   └── help.html          # Demo workflow guide
├── static/
│   └── style.css          # CCHMC-themed styles
└── deploy/
    ├── asp-alerts.service # systemd service
    └── nginx-asp-alerts.conf # nginx config
```

## API Endpoints

### Teams Callbacks (GET - redirect after action)
- `GET /api/ack/<alert_id>` - Acknowledge alert
- `GET /api/snooze/<alert_id>?hours=4` - Snooze alert

### Form Actions (POST - from dashboard)
- `POST /api/alerts/<id>/acknowledge` - Acknowledge
- `POST /api/alerts/<id>/snooze` - Snooze
- `POST /api/alerts/<id>/resolve` - Resolve with reason/notes
- `POST /api/alerts/<id>/note` - Add note

### JSON API
- `GET /api/alerts` - List alerts (with filters)
- `GET /api/alerts/<id>` - Get single alert
- `GET /api/stats` - Get alert statistics

## Pages

| Route | Description |
|-------|-------------|
| `/` | Redirect to active alerts |
| `/alerts/active` | Active (non-resolved) alerts |
| `/alerts/history` | Resolved alerts |
| `/alerts/<id>` | Single alert detail |
| `/reports` | Analytics and reports |
| `/help` | Demo workflow guide |

## Related Documentation

- [ASP Alerts Overview](../README.md)
- [Demo Workflow](../docs/demo-workflow.md)
- [Bacteremia Alerts](../asp-bacteremia-alerts/README.md)
- [Antimicrobial Usage Alerts](../antimicrobial-usage-alerts/README.md)
