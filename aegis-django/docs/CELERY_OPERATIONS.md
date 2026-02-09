# AEGIS Celery Operations Guide

## Overview

AEGIS uses Celery for background task processing across all clinical monitoring modules. Tasks are organized into three queues based on resource requirements:

| Queue | Purpose | Concurrency | Modules |
|-------|---------|-------------|---------|
| `default` | FHIR polling | 4 workers | MDRO, Drug-Bug, Dosing, Usage, Prophylaxis, Outbreak |
| `llm` | GPU-bound LLM inference | 2 workers | HAI Detection, ABX Indications, Guideline Adherence |
| `batch` | Nightly Clarity batch jobs | 1 worker | NHSN Reporting |

## Worker Startup

### Development (eager mode)

In development, `CELERY_TASK_ALWAYS_EAGER = True` — tasks run synchronously in the Django process. No workers or Redis needed.

### Production

Start Redis first, then workers per queue:

```bash
# Default queue (FHIR polling tasks)
celery -A aegis_project worker -Q default -c 4 --loglevel=info

# LLM queue (GPU-bound tasks — lower concurrency)
celery -A aegis_project worker -Q llm -c 2 --loglevel=info

# Batch queue (nightly Clarity jobs)
celery -A aegis_project worker -Q batch -c 1 --loglevel=info

# Or run all queues in a single worker (small deployments)
celery -A aegis_project worker -Q default,llm,batch -c 4 --loglevel=info
```

### Beat Scheduler

Beat manages periodic task scheduling:

```bash
# Using database scheduler (allows runtime overrides via Django admin)
celery -A aegis_project beat --scheduler django_celery_beat.schedulers:DatabaseScheduler --loglevel=info
```

### Flower (monitoring dashboard)

```bash
celery -A aegis_project flower --port=5555
```

Access at `http://localhost:5555`

## Task Schedule

### FHIR Polling (default queue)

| Task | Schedule | Description |
|------|----------|-------------|
| `monitor_mdro` | every 15 min | Detect new MDRO cases from cultures |
| `monitor_drug_bug` | every 5 min | Check for drug-bug mismatches |
| `monitor_dosing` | every 15 min | Verify dosing against rules engine |
| `monitor_usage` | every 5 min | Check broad-spectrum usage durations |
| `monitor_prophylaxis` | every 5 min | Evaluate surgical prophylaxis compliance |
| `detect_outbreaks` | every 30 min | Cluster detection on MDRO + HAI cases |

### LLM Tasks (llm queue)

| Task | Schedule | Description |
|------|----------|-------------|
| `detect_hai_candidates` | every 5 min | Rule-based HAI candidate screening |
| `classify_hai_candidates` | every 5 min | LLM classification of pending candidates |
| `check_abx_indications` | every 5 min | Extract indications, check guidelines |
| `auto_accept_old_indications` | every 1 hour | Auto-accept stale indication candidates |
| `check_guideline_triggers` | every 5 min | Detect new guideline bundle triggers |
| `check_guideline_episodes` | every 15 min | Check episode deadline violations |
| `check_guideline_adherence` | every 15 min | Run element adherence checkers |

### Batch Tasks (batch queue)

| Task | Schedule | Description |
|------|----------|-------------|
| `nhsn_nightly_extract` | 2:00 AM daily | Extract AU/AR/denominator data from Clarity |
| `nhsn_create_events` | 3:00 AM daily | Create NHSN events from confirmed HAI |

## Runtime Schedule Overrides

The `django-celery-beat` admin interface (Django admin > Periodic Tasks) allows runtime changes to schedules without code deployment. The code-defined `CELERY_BEAT_SCHEDULE` provides defaults; database entries take precedence.

## Management Commands

All monitoring management commands continue to work for ad-hoc runs:

```bash
# One-off runs (bypass Celery)
python manage.py monitor_mdro --once
python manage.py monitor_drug_bug --once --hours 48
python manage.py monitor_dosing --once
python manage.py monitor_usage --once
python manage.py monitor_prophylaxis --once
python manage.py detect_outbreaks --once
python manage.py monitor_hai --once
python manage.py monitor_indications --once
python manage.py monitor_guidelines --all --once
python manage.py nhsn_extract --all

# Continuous mode (legacy — use Celery workers instead in production)
python manage.py monitor_mdro --continuous --interval 15
```

## Configuration

### Redis

```bash
# .env
CELERY_BROKER_URL=redis://localhost:6379/0
CELERY_RESULT_BACKEND=redis://localhost:6379/0
```

### Worker Tuning

Settings in `settings/base.py`:

- `CELERY_TASK_ACKS_LATE = True` — Tasks acknowledged after completion (crash recovery)
- `CELERY_WORKER_PREFETCH_MULTIPLIER = 1` — Fair scheduling for long-running LLM tasks

### Retry Behavior

All tasks use:
- `max_retries=3`
- `autoretry_for=(ConnectionError, TimeoutError)`
- `retry_backoff=True` (exponential backoff)
- FHIR tasks: `default_retry_delay=60`
- LLM tasks: `default_retry_delay=120`
- Batch tasks: `default_retry_delay=300`

## Troubleshooting

### Check worker status

```bash
celery -A aegis_project inspect active
celery -A aegis_project inspect reserved
celery -A aegis_project inspect stats
```

### Purge queues (caution)

```bash
celery -A aegis_project purge -Q default
```

### Check Redis connectivity

```bash
redis-cli ping
redis-cli info clients
```

### Common issues

1. **Tasks not executing**: Check Redis is running and `CELERY_BROKER_URL` is correct
2. **LLM tasks timing out**: Increase `--soft-time-limit` for the llm worker
3. **Beat not scheduling**: Ensure only ONE beat process is running (multiple beats cause duplicate tasks)
4. **Tasks stuck in reserved**: Worker may have crashed — restart the worker

## Systemd Service Files

For production deployment, create systemd units:

```ini
# /etc/systemd/system/aegis-celery-default.service
[Unit]
Description=AEGIS Celery Default Worker
After=redis.service postgresql.service

[Service]
User=aegis
WorkingDirectory=/opt/aegis
ExecStart=/opt/aegis/venv/bin/celery -A aegis_project worker -Q default -c 4 --loglevel=info
Restart=always

[Install]
WantedBy=multi-user.target
```

```ini
# /etc/systemd/system/aegis-celery-beat.service
[Unit]
Description=AEGIS Celery Beat Scheduler
After=redis.service

[Service]
User=aegis
WorkingDirectory=/opt/aegis
ExecStart=/opt/aegis/venv/bin/celery -A aegis_project beat --scheduler django_celery_beat.schedulers:DatabaseScheduler --loglevel=info
Restart=always

[Install]
WantedBy=multi-user.target
```

## Not Converted to Celery

- **`run_realtime_prophylaxis`** — Stays as a systemd daemon. This is an async HL7 ADT/MLLP TCP listener that needs a persistent socket connection, not periodic scheduling.
