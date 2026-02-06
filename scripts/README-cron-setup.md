# Cron Job Setup for AEGIS Approval Recheck

## Overview

The approval recheck scheduler automatically checks antibiotics that have reached their approved end date and creates re-approval requests if the patient is still on the same antibiotic.

## Installation

### 1. Create Log Directory

```bash
sudo mkdir -p /var/log/aegis
sudo chown david:david /var/log/aegis
```

### 2. Install Cron Job

```bash
# Copy cron file to system cron directory
sudo cp /home/david/projects/aegis/scripts/cron.d/aegis-recheck /etc/cron.d/

# Set proper permissions
sudo chmod 644 /etc/cron.d/aegis-recheck

# Restart cron service
sudo systemctl restart cron
```

### 3. Verify Installation

```bash
# Check that cron file is loaded
sudo systemctl status cron

# View cron logs
sudo grep aegis-recheck /var/log/syslog
```

## Schedule

The job runs **3 times daily**:
- **6:00 AM** - Morning check for approvals ending overnight
- **12:00 PM** - Midday check
- **6:00 PM** - Evening check

## Configuration

The recheck script reads configuration from environment variables. You can set these in:
- `/etc/environment` (system-wide)
- `~/.bashrc` or `~/.profile` (user-specific)
- A separate env file loaded by the cron job

### Required Environment Variables

```bash
# Database path
ABX_APPROVALS_DB_PATH=/home/david/.aegis/abx_approvals.db

# FHIR server
FHIR_BASE_URL=http://localhost:8081/fhir

# Email notifications (optional)
SMTP_SERVER=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=your-email@hospital.org
SMTP_PASSWORD=your-password
ASP_EMAIL_FROM=asp-alerts@hospital.org
ASP_EMAIL_TO=asp-team@hospital.org,id-team@hospital.org
```

### Using Environment File with Cron

To use an environment file:

1. Create `/home/david/projects/aegis/.env.production`:
```bash
ABX_APPROVALS_DB_PATH=/home/david/.aegis/abx_approvals.db
FHIR_BASE_URL=http://localhost:8081/fhir
# ... other variables
```

2. Update cron job to source the file:
```cron
0 6,12,18 * * * david bash -c 'source /home/david/projects/aegis/.env.production && /usr/bin/python3 /home/david/projects/aegis/scripts/run_approval_recheck.py' >> /var/log/aegis/recheck.log 2>&1
```

## Monitoring

### View Logs

```bash
# View recent logs
tail -f /var/log/aegis/recheck.log

# View today's logs
grep "$(date +%Y-%m-%d)" /var/log/aegis/recheck.log

# Count re-approvals created today
grep "Re-approvals created" /var/log/aegis/recheck.log | tail -3
```

### Log Rotation

Create `/etc/logrotate.d/aegis`:

```
/var/log/aegis/*.log {
    daily
    rotate 30
    compress
    delaycompress
    missingok
    notifempty
    create 0644 david david
}
```

## Manual Testing

Run the script manually to test:

```bash
# Activate environment if needed
source /home/david/projects/aegis/.env.production

# Run script
python3 /home/david/projects/aegis/scripts/run_approval_recheck.py
```

## Troubleshooting

### Check if cron job is running

```bash
# View cron status
sudo systemctl status cron

# Check syslog for cron execution
sudo grep CRON /var/log/syslog | grep aegis-recheck
```

### Common Issues

1. **Script not executing**
   - Check cron file permissions: `ls -l /etc/cron.d/aegis-recheck`
   - Should be: `-rw-r--r-- root root`

2. **Python import errors**
   - Ensure Python path is correct in script
   - Check that common modules are accessible

3. **FHIR connection errors**
   - Verify FHIR_BASE_URL is correct
   - Check that FHIR server is running
   - Test connection: `curl $FHIR_BASE_URL/metadata`

4. **Email not sending**
   - Verify SMTP settings
   - Check SMTP credentials
   - Test email manually first

## Disabling the Job

To temporarily disable:

```bash
# Comment out the cron line
sudo vim /etc/cron.d/aegis-recheck
# Add # at start of line

# Or remove the file entirely
sudo rm /etc/cron.d/aegis-recheck
sudo systemctl restart cron
```
