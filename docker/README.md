# AEGIS Docker Infrastructure

This directory contains Docker configurations for the AEGIS Flask → Django migration.

## Quick Start

```bash
# 1. Setup environment (creates .env with secure passwords)
./scripts/setup_dev_environment.sh

# 2. Start all services
docker-compose up -d

# 3. Check service health
docker-compose ps

# 4. View logs
docker-compose logs -f django celery nginx
```

## Services

| Service | Port | Purpose | URL |
|---------|------|---------|-----|
| **nginx** | 8080 (HTTP), 8443 (HTTPS) | Reverse proxy with path-based routing | http://localhost:8080 |
| **flask** | 8082 | Legacy Flask application | http://localhost:8082 |
| **django** | 8000 | New Django application | http://localhost:8000 |
| **postgres** | 5432 | Shared PostgreSQL database | localhost:5432 |
| **redis** | 6379 | Celery broker + cache | localhost:6379 |
| **celery** | - | Background task worker | - |
| **celery-beat** | - | Periodic task scheduler | - |
| **flower** | 5555 | Celery monitoring UI | http://localhost:5555 |
| **hapi-fhir** | 8081 | FHIR server (dev only) | http://localhost:8081 |

## Files

```
docker/
├── Dockerfile.django       # Django production container
├── Dockerfile.flask        # Flask container (migration period)
├── nginx/
│   ├── nginx.conf          # Main nginx config
│   └── conf.d/
│       └── aegis.conf      # Path-based routing config
└── README.md               # This file
```

## Common Commands

### Managing Services

```bash
# Start specific services
docker-compose up -d postgres redis django

# Restart a service
docker-compose restart django

# Stop all services
docker-compose down

# Stop and remove volumes (clean slate)
docker-compose down -v

# Scale Celery workers
docker-compose up -d --scale celery=4
```

### Viewing Logs

```bash
# All services
docker-compose logs -f

# Specific service
docker-compose logs -f django

# Last 100 lines
docker-compose logs --tail=100 celery

# Since 1 hour ago
docker-compose logs --since 1h nginx
```

### Executing Commands

```bash
# Django migrations
docker-compose exec django python manage.py migrate

# Django shell
docker-compose exec django python manage.py shell

# Create Django superuser
docker-compose exec django python manage.py createsuperuser

# PostgreSQL shell
docker-compose exec postgres psql -U aegis_user -d aegis

# Redis CLI
docker-compose exec redis redis-cli

# Celery inspect
docker-compose exec celery celery -A aegis_project inspect active
```

### Nginx Operations

```bash
# Test nginx config
docker-compose exec nginx nginx -t

# Reload nginx (zero downtime)
docker-compose exec nginx nginx -s reload

# View nginx access log
docker-compose exec nginx tail -f /var/log/nginx/access.log

# View nginx error log
docker-compose exec nginx tail -f /var/log/nginx/error.log
```

## Module Cutover

Use the cutover script to route modules from Flask to Django:

```bash
# Check current routing
./scripts/nginx_cutover.sh dosing-verification status

# Cutover to Django
./scripts/nginx_cutover.sh dosing-verification cutover

# Rollback to Flask
./scripts/nginx_cutover.sh dosing-verification rollback
```

## Development Workflow

### 1. Code Changes

For Django changes:
```bash
# Django auto-reloads in development mode
docker-compose restart django  # Only if needed
```

For Flask changes:
```bash
# Flask auto-reloads in development mode
docker-compose restart flask  # Only if needed
```

For Nginx changes:
```bash
# Edit docker/nginx/conf.d/aegis.conf
docker-compose exec nginx nginx -t  # Test
docker-compose exec nginx nginx -s reload  # Apply
```

### 2. Database Migrations

```bash
# Create migration
docker-compose exec django python manage.py makemigrations

# Apply migration
docker-compose exec django python manage.py migrate

# Show migration status
docker-compose exec django python manage.py showmigrations
```

### 3. Celery Tasks

```bash
# View active tasks
docker-compose exec celery celery -A aegis_project inspect active

# View scheduled tasks
docker-compose exec celery celery -A aegis_project inspect scheduled

# Purge all pending tasks
docker-compose exec celery celery -A aegis_project purge

# Restart workers
docker-compose restart celery celery-beat
```

## Troubleshooting

### Service won't start

```bash
# Check logs for errors
docker-compose logs <service-name>

# Check container status
docker-compose ps

# Rebuild container
docker-compose build --no-cache <service-name>
docker-compose up -d <service-name>
```

### Database connection issues

```bash
# Check PostgreSQL is healthy
docker-compose exec postgres pg_isready -U aegis_user -d aegis

# Check connection from Django
docker-compose exec django python manage.py check --database default

# View database logs
docker-compose logs postgres
```

### Nginx routing issues

```bash
# Test nginx config
docker-compose exec nginx nginx -t

# View routing config
docker-compose exec nginx cat /etc/nginx/conf.d/aegis.conf

# Check which backend handled request (in access logs)
docker-compose logs nginx | grep "GET /dosing-verification"
```

### Celery not processing tasks

```bash
# Check workers are running
docker-compose ps celery

# Check worker logs
docker-compose logs celery

# Check Redis connection
docker-compose exec celery python -c "from aegis_project.celery import app; print(app.control.inspect().active())"

# Restart workers
docker-compose restart celery celery-beat
```

### Clean up and reset

```bash
# Stop all services
docker-compose down

# Remove volumes (WARNING: deletes all data)
docker-compose down -v

# Remove images
docker-compose down --rmi all

# Full reset
docker-compose down -v --rmi all
rm -rf data/  # If you have local data directory
./scripts/setup_dev_environment.sh  # Start fresh
```

## Production Deployment

For production, use `docker-compose.prod.yml`:

```bash
# Pull latest images
docker-compose -f docker-compose.prod.yml pull

# Start services
docker-compose -f docker-compose.prod.yml up -d

# Check status
docker-compose -f docker-compose.prod.yml ps
```

See `docs/DEVOPS_STRATEGY.md` for complete production deployment guide.

## Health Checks

All services include health checks:

```bash
# Check all service health
docker-compose ps

# Manual health checks
curl http://localhost:8080/health          # Nginx
curl http://localhost:8082/health          # Flask
curl http://localhost:8000/health/         # Django
curl http://localhost:8081/fhir/metadata   # HAPI FHIR
```

## Security Notes

- `.env` file contains sensitive passwords - never commit to Git
- Default passwords are auto-generated by setup script
- For production, use secrets management (Docker secrets, Vault, etc.)
- All containers run as non-root user
- Use `docker-compose.prod.yml` for production (different security settings)

## Performance Tuning

### Django Workers

```yaml
# In docker-compose.yml
django:
  command: gunicorn --workers 8 --threads 4 ...
```

### Celery Concurrency

```bash
# Scale workers
docker-compose up -d --scale celery=4

# Or adjust concurrency
docker-compose exec celery celery -A aegis_project control pool_grow 2
```

### PostgreSQL

```bash
# Adjust shared_buffers, work_mem in postgres config
# Edit docker/postgres/postgresql.conf
```

## Monitoring

- **Flower (Celery)**: http://localhost:5555
- **Django Admin**: http://localhost:8000/admin/
- **Logs**: `docker-compose logs -f`
- **Metrics**: Prometheus exporters (see `docs/DEVOPS_STRATEGY.md`)

## Getting Help

1. Check logs: `docker-compose logs <service>`
2. Check health: `docker-compose ps`
3. Read full DevOps strategy: `docs/DEVOPS_STRATEGY.md`
4. Contact DevOps Specialist for infrastructure issues
5. Contact Django Architect for application issues

## Next Steps

1. Wait for Django Architect to create `aegis-django/` structure
2. Run `docker-compose up -d` to start environment
3. Test Flask access: http://localhost:8080
4. Test Django access: http://localhost:8080/admin/
5. Begin migrating first module (Action Analytics recommended)
