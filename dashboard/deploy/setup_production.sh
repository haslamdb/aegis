#!/bin/bash
# AEGIS Dashboard - Production Setup Script
#
# Usage:
#   ./setup_production.sh [domain]
#
# Example:
#   ./setup_production.sh aegis.example.com

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
DOMAIN="${1:-aegis.local}"

echo "=============================================="
echo "AEGIS Dashboard - Production Setup"
echo "=============================================="
echo "Domain: $DOMAIN"
echo "Project: $PROJECT_DIR"
echo ""

# Check if running as appropriate user
if [ "$EUID" -eq 0 ]; then
    echo "Warning: Running as root. Service will run as user 'david'."
fi

# Create logs directory
echo "Creating logs directory..."
mkdir -p "$PROJECT_DIR/logs"

# Create .env if it doesn't exist
if [ ! -f "$PROJECT_DIR/.env" ]; then
    echo "Creating .env from template..."
    cp "$PROJECT_DIR/.env.template" "$PROJECT_DIR/.env"
    echo "  Please edit $PROJECT_DIR/.env with your settings"
fi

# Install systemd service
echo "Installing systemd service..."
sudo cp "$SCRIPT_DIR/aegis.service" /etc/systemd/system/
sudo systemctl daemon-reload

# Determine nginx config to use
if [ "$DOMAIN" = "aegis.local" ] || [[ "$DOMAIN" =~ ^192\. ]] || [[ "$DOMAIN" =~ ^10\. ]]; then
    NGINX_CONF="nginx-aegis-local.conf"
    echo "Using local nginx configuration..."
else
    NGINX_CONF="nginx-aegis-external.conf"
    echo "Using external nginx configuration..."

    # Replace domain placeholder
    sed "s/YOUR_DOMAIN/$DOMAIN/g" "$SCRIPT_DIR/$NGINX_CONF" > "/tmp/aegis-nginx.conf"
    NGINX_CONF="/tmp/aegis-nginx.conf"
fi

# Install nginx configuration
echo "Installing nginx configuration..."
if [ -f "/tmp/aegis-nginx.conf" ]; then
    sudo cp "/tmp/aegis-nginx.conf" /etc/nginx/sites-available/aegis
else
    sudo cp "$SCRIPT_DIR/$NGINX_CONF" /etc/nginx/sites-available/aegis
fi

# Enable site
if [ ! -L /etc/nginx/sites-enabled/aegis ]; then
    sudo ln -s /etc/nginx/sites-available/aegis /etc/nginx/sites-enabled/
fi

# Test nginx configuration
echo "Testing nginx configuration..."
sudo nginx -t

# Start/restart services
echo "Starting services..."
sudo systemctl enable aegis
sudo systemctl restart aegis
sudo systemctl reload nginx

# Check status
echo ""
echo "=============================================="
echo "Setup complete!"
echo "=============================================="
echo ""
echo "Service status:"
sudo systemctl status aegis --no-pager -l | head -15
echo ""
echo "Access URLs:"
if [ "$DOMAIN" = "aegis.local" ]; then
    echo "  Local: http://aegis.local/"
    echo "  IP:    http://$(hostname -I | awk '{print $1}')/"
else
    echo "  https://$DOMAIN/"
fi
echo ""
echo "Useful commands:"
echo "  sudo systemctl status aegis   # Check service status"
echo "  sudo systemctl restart aegis  # Restart service"
echo "  sudo journalctl -u aegis -f   # View live logs"
echo "  tail -f $PROJECT_DIR/logs/aegis.log"
