#!/bin/bash
# AEGIS Django - Staging Deployment Setup
# Run as root (or with sudo) on the target server
#
# Usage: sudo bash deploy/setup-staging.sh
#
# Prerequisites:
#   - DNS A record: staging.aegis-asp.com → server public IP
#   - This script is run from the aegis-django/ directory

set -euo pipefail

AEGIS_DIR="/home/david/projects/aegis/aegis-django"
AEGIS_USER="david"
AEGIS_GROUP="david"

echo "=== AEGIS Django Staging Setup ==="

# ─── WP1: PostgreSQL 16 + ZFS ────────────────────────────────────

echo ""
echo "--- WP1: PostgreSQL 16 + ZFS ---"

# Install PostgreSQL 16 first (creates postgres user)
if ! dpkg -l postgresql-16 &>/dev/null; then
    echo "Installing PostgreSQL 16..."
    apt-get update -qq
    apt-get install -y -qq postgresql-16 postgresql-client-16
else
    echo "PostgreSQL 16 already installed"
fi

# Create ZFS dataset for PostgreSQL
if ! zfs list fastpool/postgres &>/dev/null; then
    echo "Creating ZFS dataset fastpool/postgres..."
    zfs create -o recordsize=8k -o compression=lz4 -o atime=off -o primarycache=metadata fastpool/postgres
fi
chown postgres:postgres /fastpool/postgres

# Configure PostgreSQL data directory on ZFS
PG_CONF="/etc/postgresql/16/main/postgresql.conf"
if ! grep -q "fastpool/postgres" "$PG_CONF" 2>/dev/null; then
    echo "Moving PostgreSQL data to ZFS..."
    systemctl stop postgresql

    # Initialize data directory on ZFS if empty
    if [ ! -f /fastpool/postgres/PG_VERSION ]; then
        # Copy existing data or initialize fresh
        if [ -d /var/lib/postgresql/16/main/base ]; then
            rsync -a /var/lib/postgresql/16/main/ /fastpool/postgres/
        else
            sudo -u postgres /usr/lib/postgresql/16/bin/initdb -D /fastpool/postgres
        fi
    fi
    chown -R postgres:postgres /fastpool/postgres

    # Update config
    sed -i "s|^data_directory = .*|data_directory = '/fastpool/postgres'|" "$PG_CONF"
    systemctl start postgresql
else
    echo "PostgreSQL already configured for ZFS"
fi

# Create database and user
echo "Setting up aegis database..."
DB_PASSWORD=$(python3 -c "import secrets; print(secrets.token_urlsafe(32))")

sudo -u postgres psql -tc "SELECT 1 FROM pg_roles WHERE rolname='aegis'" | grep -q 1 || \
    sudo -u postgres psql -c "CREATE USER aegis WITH PASSWORD '$DB_PASSWORD';"

sudo -u postgres psql -tc "SELECT 1 FROM pg_database WHERE datname='aegis_django'" | grep -q 1 || \
    sudo -u postgres psql -c "CREATE DATABASE aegis_django OWNER aegis;"

# Configure pg_hba.conf for local md5 auth
PG_HBA="/etc/postgresql/16/main/pg_hba.conf"
if ! grep -q "aegis" "$PG_HBA" 2>/dev/null; then
    # Insert before the first "local" line
    sed -i '/^local\s\+all\s\+all/i local   aegis_django    aegis                                   md5' "$PG_HBA"
    systemctl reload postgresql
fi

echo "PostgreSQL setup complete"
echo "  DB Password: $DB_PASSWORD"
echo "  (Save this — you'll need it for .env)"

# ─── WP2: Redis ──────────────────────────────────────────────────

echo ""
echo "--- WP2: Redis ---"

if ! dpkg -l redis-server &>/dev/null; then
    echo "Installing Redis..."
    apt-get install -y -qq redis-server
else
    echo "Redis already installed"
fi

# Configure Redis
REDIS_CONF="/etc/redis/redis.conf"
if ! grep -q "maxmemory 2gb" "$REDIS_CONF" 2>/dev/null; then
    echo "Configuring Redis..."
    sed -i 's/^bind .*/bind 127.0.0.1 ::1/' "$REDIS_CONF"
    # Set maxmemory
    if grep -q "^# maxmemory " "$REDIS_CONF"; then
        sed -i 's/^# maxmemory .*/maxmemory 2gb/' "$REDIS_CONF"
    else
        echo "maxmemory 2gb" >> "$REDIS_CONF"
    fi
    # Set eviction policy
    if grep -q "^# maxmemory-policy" "$REDIS_CONF"; then
        sed -i 's/^# maxmemory-policy .*/maxmemory-policy allkeys-lru/' "$REDIS_CONF"
    else
        echo "maxmemory-policy allkeys-lru" >> "$REDIS_CONF"
    fi
fi

systemctl enable --now redis-server
systemctl restart redis-server
echo "Redis setup complete"

# ─── WP3: Directories & Virtualenv ──────────────────────────────

echo ""
echo "--- WP3: Directories & Dependencies ---"

# Create directories
mkdir -p /var/log/aegis
chown "$AEGIS_USER:$AEGIS_GROUP" /var/log/aegis

mkdir -p /var/www/aegis-django/static
mkdir -p /var/www/aegis-django/media
chown -R "$AEGIS_USER:$AEGIS_GROUP" /var/www/aegis-django

mkdir -p /run/user/1000/celery
chown "$AEGIS_USER:$AEGIS_GROUP" /run/user/1000/celery

# Install staging requirements
echo "Installing Python dependencies..."
sudo -u "$AEGIS_USER" "$AEGIS_DIR/venv/bin/pip" install -q -r "$AEGIS_DIR/requirements/staging.txt"

echo "Directories and dependencies ready"

# ─── WP4: Generate .env ─────────────────────────────────────────

echo ""
echo "--- WP4: Generating .env ---"

ENV_FILE="$AEGIS_DIR/.env"
if [ ! -f "$ENV_FILE" ]; then
    SECRET_KEY=$(python3 -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())" 2>/dev/null || python3 -c "import secrets; print(secrets.token_urlsafe(50))")
    cat > "$ENV_FILE" << EOF
DJANGO_SETTINGS_MODULE=aegis_project.settings.staging
SECRET_KEY=$SECRET_KEY
DB_NAME=aegis_django
DB_USER=aegis
DB_PASSWORD=$DB_PASSWORD
DB_HOST=localhost
DB_PORT=5432
CELERY_BROKER_URL=redis://localhost:6379/0
CELERY_RESULT_BACKEND=redis://localhost:6379/0
REDIS_URL=redis://localhost:6379/1
ALLOWED_HOSTS=staging.aegis-asp.com
CORS_ALLOWED_ORIGINS=https://staging.aegis-asp.com
ENVIRONMENT=staging
EOF
    chown "$AEGIS_USER:$AEGIS_GROUP" "$ENV_FILE"
    chmod 600 "$ENV_FILE"
    echo ".env created with generated credentials"
else
    echo ".env already exists — skipping (update DB_PASSWORD manually if needed)"
    echo "  New DB password: $DB_PASSWORD"
fi

# ─── WP5: Systemd Services ──────────────────────────────────────

echo ""
echo "--- WP5: Systemd Services ---"

cp "$AEGIS_DIR/deploy/systemd/aegis-django.service" /etc/systemd/system/
cp "$AEGIS_DIR/deploy/systemd/aegis-celery.service" /etc/systemd/system/
cp "$AEGIS_DIR/deploy/systemd/aegis-celerybeat.service" /etc/systemd/system/

systemctl daemon-reload
echo "Systemd units installed"

# ─── WP6: Django Setup ──────────────────────────────────────────

echo ""
echo "--- WP6: Django Migrate & Static ---"

cd "$AEGIS_DIR"
sudo -u "$AEGIS_USER" "$AEGIS_DIR/venv/bin/python" manage.py migrate 2>/dev/null
sudo -u "$AEGIS_USER" "$AEGIS_DIR/venv/bin/python" manage.py collectstatic --noinput 2>/dev/null
echo "Migrations and static files complete"

echo ""
echo "Create a superuser:"
echo "  cd $AEGIS_DIR && venv/bin/python manage.py createsuperuser"

# ─── WP7: Start Services ────────────────────────────────────────

echo ""
echo "--- WP7: Starting Services ---"

systemctl enable aegis-django aegis-celery aegis-celerybeat
systemctl start aegis-django
systemctl start aegis-celery
systemctl start aegis-celerybeat

echo "Services started"

# ─── WP8: Nginx ─────────────────────────────────────────────────

echo ""
echo "--- WP8: Nginx ---"

# Install HTTP-only version first for certbot challenge
NGINX_CONF="/etc/nginx/sites-available/aegis-django-staging"
if [ ! -f "$NGINX_CONF" ]; then
    # Start with HTTP-only for certbot
    cat > "$NGINX_CONF" << 'NGINX_EOF'
server {
    listen 80;
    listen [::]:80;
    server_name staging.aegis-asp.com;

    location /.well-known/acme-challenge/ {
        root /var/www/certbot;
    }

    location / {
        proxy_pass http://127.0.0.1:8083;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
NGINX_EOF

    ln -sf "$NGINX_CONF" /etc/nginx/sites-enabled/aegis-django-staging
    mkdir -p /var/www/certbot
    nginx -t && systemctl reload nginx
    echo "HTTP-only nginx config installed"

    echo ""
    echo "Now run certbot to get TLS certificate:"
    echo "  sudo certbot --nginx -d staging.aegis-asp.com"
    echo ""
    echo "After certbot succeeds, replace nginx config with full version:"
    echo "  sudo cp $AEGIS_DIR/deploy/nginx/aegis-django-staging $NGINX_CONF"
    echo "  sudo nginx -t && sudo systemctl reload nginx"
else
    echo "Nginx config already exists"
fi

# ─── Summary ─────────────────────────────────────────────────────

echo ""
echo "========================================="
echo "  AEGIS Django Staging Setup Complete"
echo "========================================="
echo ""
echo "Next steps:"
echo "  1. Verify DNS A record: staging.aegis-asp.com → server IP"
echo "  2. Run certbot: sudo certbot --nginx -d staging.aegis-asp.com"
echo "  3. Install full nginx config: sudo cp $AEGIS_DIR/deploy/nginx/aegis-django-staging $NGINX_CONF"
echo "  4. Create superuser: cd $AEGIS_DIR && venv/bin/python manage.py createsuperuser"
echo "  5. Verify: curl -s http://staging.aegis-asp.com/health/"
echo ""
echo "Service management:"
echo "  systemctl status aegis-django aegis-celery aegis-celerybeat"
echo "  journalctl -u aegis-django -f"
echo ""
