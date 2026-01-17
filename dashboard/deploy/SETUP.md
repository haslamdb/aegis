# ASP Alerts Dashboard - Deployment Guide

Deploy the dashboard at `https://alerts.asp-ai-agent.com`

## Prerequisites

- This machine already runs `asp-ai-agent.com` with nginx
- Port 8082 is free (dashboard Flask app)
- You have access to your DNS provider
- You have access to Unifi controller

---

## Step 1: DNS Configuration

Add an A record for the subdomain pointing to your external IP.

**In your DNS provider (e.g., Cloudflare, Namecheap, etc.):**

| Type | Name | Value | TTL |
|------|------|-------|-----|
| A | alerts | 50.5.30.133 | Auto |

This creates `alerts.asp-ai-agent.com` → `50.5.30.133`

**Verify DNS (may take a few minutes to propagate):**
```bash
dig alerts.asp-ai-agent.com +short
# Should return: 50.5.30.133
```

---

## Step 2: Unifi Port Forwarding

Since asp-ai-agent already uses ports 80/443, we need to ensure traffic for the subdomain reaches this server. If both domains use the same external IP and ports, nginx will route based on the hostname.

**If ports 80/443 are already forwarded (likely):**
- No additional port forwarding needed
- nginx handles routing based on `server_name`

**If you need to add/verify port forwarding:**

1. Open Unifi Controller (https://unifi.ui.com or local controller)
2. Go to **Settings** → **Firewall & Security** → **Port Forwarding**
3. Verify or add these rules:

| Name | From | Port | Forward IP | Forward Port | Protocol |
|------|------|------|------------|--------------|----------|
| HTTP | Any | 80 | 192.168.1.163 | 80 | TCP |
| HTTPS | Any | 443 | 192.168.1.163 | 443 | TCP |

*(Replace 192.168.1.163 with this server's internal IP if different)*

**To find this server's internal IP:**
```bash
hostname -I | awk '{print $1}'
```

---

## Step 3: Install the Dashboard Service

```bash
cd ~/projects/asp-alerts/dashboard

# Create logs directory
mkdir -p logs

# Ensure .env exists
cp .env.template .env
# Edit .env if needed: nano .env

# Install systemd service
sudo cp deploy/asp-alerts.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable asp-alerts
sudo systemctl start asp-alerts

# Verify it's running
sudo systemctl status asp-alerts
curl http://localhost:8082/  # Should return HTML
```

---

## Step 4: Get SSL Certificate

**Option A: HTTP-01 Challenge (if port 80 is accessible)**

First, install the nginx config without SSL to allow the challenge:
```bash
# Temporary config for cert generation
cat << 'EOF' | sudo tee /etc/nginx/sites-available/asp-alerts
server {
    listen 80;
    server_name alerts.asp-ai-agent.com;

    location /.well-known/acme-challenge/ {
        root /var/www/certbot;
    }

    location / {
        return 200 'Waiting for SSL setup';
        add_header Content-Type text/plain;
    }
}
EOF

sudo ln -sf /etc/nginx/sites-available/asp-alerts /etc/nginx/sites-enabled/
sudo mkdir -p /var/www/certbot
sudo nginx -t && sudo systemctl reload nginx
```

Get the certificate:
```bash
sudo certbot certonly \
    --webroot \
    --webroot-path=/var/www/certbot \
    --email dbhaslam@gmail.com \
    --agree-tos \
    --no-eff-email \
    -d alerts.asp-ai-agent.com
```

**Option B: DNS-01 Challenge (if port 80 is blocked)**
```bash
sudo certbot certonly \
    --manual \
    --preferred-challenges dns \
    --email dbhaslam@gmail.com \
    --agree-tos \
    --no-eff-email \
    -d alerts.asp-ai-agent.com
```
Follow the prompts to add a TXT record to your DNS.

---

## Step 5: Install Full Nginx Configuration

```bash
# Copy the production nginx config
sudo cp ~/projects/asp-alerts/dashboard/deploy/nginx-asp-alerts.conf \
    /etc/nginx/sites-available/asp-alerts

# Test and reload
sudo nginx -t
sudo systemctl reload nginx
```

---

## Step 6: Verify Everything Works

```bash
# Check services
sudo systemctl status asp-alerts
sudo systemctl status nginx

# Test locally
curl -I http://localhost:8082/

# Test externally (from another machine or use curl with host header)
curl -I https://alerts.asp-ai-agent.com/
```

Open in browser: **https://alerts.asp-ai-agent.com/**

---

## Quick Reference

**Service Management:**
```bash
sudo systemctl status asp-alerts     # Check status
sudo systemctl restart asp-alerts    # Restart Flask
sudo systemctl reload nginx          # Reload nginx config
```

**Logs:**
```bash
# Application logs
tail -f ~/projects/asp-alerts/dashboard/logs/asp-alerts.log
tail -f ~/projects/asp-alerts/dashboard/logs/asp-alerts-error.log

# Nginx logs
sudo tail -f /var/log/nginx/asp-alerts-access.log
sudo tail -f /var/log/nginx/asp-alerts-error.log

# Systemd journal
sudo journalctl -u asp-alerts -f
```

**SSL Certificate Renewal:**
```bash
# Test renewal
sudo certbot renew --dry-run

# Force renewal
sudo certbot renew
```

---

## Troubleshooting

### "Connection refused" on port 8082
```bash
# Check if Flask is running
sudo systemctl status asp-alerts
sudo journalctl -u asp-alerts -n 50

# Check port
ss -tlnp | grep 8082
```

### SSL certificate errors
```bash
# Check cert exists
sudo ls -la /etc/letsencrypt/live/alerts.asp-ai-agent.com/

# Check cert expiry
sudo certbot certificates
```

### nginx "502 Bad Gateway"
```bash
# Flask not running or wrong port
curl http://127.0.0.1:8082/
sudo systemctl restart asp-alerts
```

### DNS not resolving
```bash
# Check propagation
dig alerts.asp-ai-agent.com +short
nslookup alerts.asp-ai-agent.com

# May need to wait or flush DNS cache
```
