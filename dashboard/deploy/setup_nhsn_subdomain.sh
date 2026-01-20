#!/bin/bash
# Setup script for NHSN subdomain redirect: nhsn.aegis-asp.com
#
# NOTE: The nhsn subdomain is DEPRECATED. This script sets up redirects
# to the main domain at aegis-asp.com. The NHSN functionality is now at:
# - https://aegis-asp.com/hai-detection/ (candidate review)
# - https://aegis-asp.com/nhsn-reporting/ (data submission)
#
# Prerequisites:
# 1. DNS A record for nhsn.aegis-asp.com pointing to this server
# 2. Main AEGIS dashboard already running at aegis-asp.com
#
# Usage: sudo ./setup_nhsn_subdomain.sh

set -e

DOMAIN="nhsn.aegis-asp.com"
MAIN_DOMAIN="aegis-asp.com"
NGINX_CONF="/etc/nginx/sites-available/nhsn-aegis"
CERTBOT_WEBROOT="/var/www/certbot"

echo "=== NHSN Subdomain Redirect Setup ==="
echo "Domain: $DOMAIN"
echo "Redirects to: $MAIN_DOMAIN"
echo ""
echo "NOTE: This subdomain is deprecated. All traffic will be redirected."
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
cp "$(dirname "$0")/nginx-nhsn-aegis.conf" $NGINX_CONF

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
        return 301 https://$MAIN_DOMAIN\$request_uri;
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
echo "NHSN subdomain ($DOMAIN) now redirects to https://$MAIN_DOMAIN"
echo ""
echo "NHSN functionality is available at:"
echo "  - https://$MAIN_DOMAIN/hai-detection/ (candidate review)"
echo "  - https://$MAIN_DOMAIN/nhsn-reporting/ (data submission)"
echo ""
