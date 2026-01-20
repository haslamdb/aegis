#!/bin/bash
# Setup script for NHSN subdomain: nhsn.aegis-asp.com
#
# Prerequisites:
# 1. DNS A record for nhsn.aegis-asp.com pointing to this server
# 2. Port 8444 open in firewall
# 3. Main AEGIS dashboard already running on port 8082
#
# Usage: sudo ./setup_nhsn_subdomain.sh

set -e

DOMAIN="nhsn.aegis-asp.com"
NGINX_CONF="/etc/nginx/sites-available/nhsn-aegis"
CERTBOT_WEBROOT="/var/www/certbot"

echo "=== NHSN Subdomain Setup ==="
echo "Domain: $DOMAIN"
echo ""

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    echo "Please run as root (sudo)"
    exit 1
fi

# Step 1: Create certbot webroot if needed
echo "[1/5] Creating certbot webroot..."
mkdir -p $CERTBOT_WEBROOT

# Step 2: Copy nginx config
echo "[2/5] Installing nginx configuration..."
cp "$(dirname "$0")/nginx-nhsn.conf" $NGINX_CONF

# Step 3: Create temporary config for SSL certificate
echo "[3/5] Creating temporary config for SSL..."
cat > /etc/nginx/sites-available/nhsn-temp << EOF
server {
    listen 80;
    server_name $DOMAIN;

    location /.well-known/acme-challenge/ {
        root $CERTBOT_WEBROOT;
    }

    location / {
        return 200 'Waiting for SSL setup';
        add_header Content-Type text/plain;
    }
}
EOF

# Enable temporary config
ln -sf /etc/nginx/sites-available/nhsn-temp /etc/nginx/sites-enabled/nhsn-temp
nginx -t && systemctl reload nginx

# Step 4: Get SSL certificate
echo "[4/5] Obtaining SSL certificate..."
echo "Make sure DNS is configured for $DOMAIN before proceeding."
read -p "Press Enter when DNS is ready, or Ctrl+C to cancel..."

certbot certonly --webroot \
    -w $CERTBOT_WEBROOT \
    -d $DOMAIN \
    --non-interactive \
    --agree-tos \
    --email admin@aegis-asp.com \
    || {
        echo "Certbot failed. You may need to run manually:"
        echo "  sudo certbot certonly --webroot -w $CERTBOT_WEBROOT -d $DOMAIN"
        exit 1
    }

# Step 5: Enable full config
echo "[5/5] Enabling production configuration..."
rm -f /etc/nginx/sites-enabled/nhsn-temp
rm -f /etc/nginx/sites-available/nhsn-temp
ln -sf $NGINX_CONF /etc/nginx/sites-enabled/nhsn-aegis

# Test and reload
nginx -t && systemctl reload nginx

echo ""
echo "=== Setup Complete ==="
echo ""
echo "NHSN Dashboard available at: https://$DOMAIN:8444"
echo ""
echo "To verify:"
echo "  curl -I https://$DOMAIN:8444/nhsn/"
echo ""
echo "Don't forget to update your environment:"
echo "  DASHBOARD_BASE_URL=https://$DOMAIN:8444"
echo ""
