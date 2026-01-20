# AEGIS Dashboard Reorganization - Status

**Date:** 2026-01-19

## Completed

1. **Dashboard reorganization** - Restructured into 4 sections:
   - Landing page at `/` with 4 section cards
   - ASP Alerts at `/asp-alerts`
   - HAI Detection at `/hai-detection`
   - NHSN Reporting at `/nhsn-reporting`
   - Dashboards at `/dashboards` (placeholder)

2. **NHSN Reporting Fixed:**
   - Issue: systemd service wasn't running, nginx couldn't proxy to port 8082
   - Solution: Started Flask manually on port 8082
   - Data now displaying correctly (189 DOT, 689.78 rate)
   - Rebranded "ASP Alerts" to "AEGIS" throughout

3. **Unified NHSN Submission Page** (2026-01-19):
   - Moved HAI submission from HAI Detection to NHSN Reporting
   - Created unified submission page with 3 tabs:
     - **AU** - Antibiotic Usage (monthly)
     - **AR** - Antimicrobial Resistance (quarterly)
     - **HAI** - Healthcare-Associated Infections (HAI events like CLABSI)
   - Old URL `/hai-detection/submission` now redirects to `/nhsn-reporting/submission?type=hai`
   - Removed Submission link from HAI Detection navigation

   Files modified:
   - `dashboard/routes/au_ar.py` - Added HAI submission routes
   - `dashboard/routes/nhsn.py` - Removed submission routes, added redirect
   - `dashboard/templates/nhsn_submission_unified.html` - New unified template
   - `dashboard/templates/base.html` - Updated HAI Detection nav

4. **HAI Detail Page** (2026-01-19):
   - Added HAI Detail page to NHSN Reporting navigation
   - Shows confirmed HAI events by type and location for current reporting period
   - Added filters for date range and HAI type
   - Fixed data propagation bug on HAI submission page (events now load with default dates)

   Files modified:
   - `dashboard/routes/au_ar.py` - Added hai_detail route
   - `dashboard/templates/hai_detail.html` - New HAI detail template
   - `dashboard/templates/base.html` - Added HAI Detail nav link

5. **Documentation Update** (2026-01-19):
   - Updated top-level README.md with new URL structure
   - Updated dashboard/README.md with all section routes
   - Updated nhsn-reporting/README.md with new dashboard integration paths
   - Dashboards page already had "Coming Soon" placeholder

## Current Structure

### HAI Detection (`/hai-detection/`)
- Dashboard - CLABSI candidates awaiting review
- History - Resolved candidates
- Reports - HAI analytics and override stats
- Help

### NHSN Reporting (`/nhsn-reporting/`)
- Dashboard - AU/AR overview with current month stats
- AU Detail - Detailed antibiotic usage by location
- AR Detail - Antimicrobial resistance phenotypes
- Denominators - Patient days by location
- Submission - **Unified page for AU, AR, and HAI submissions**
- Help

## To Make Permanent

Run with sudo to restart the systemd service:
```bash
sudo systemctl restart aegis
```

## Production File Locations

- **Static CSS**: `/var/www/aegis/static/style.css`
- **Service file**: `/etc/systemd/system/aegis.service`
- **Nginx config**: `/etc/nginx/sites-available/aegis`

To update CSS in production:
```bash
sudo cp dashboard/static/style.css /var/www/aegis/static/
```

## Access URLs

- Landing: `https://aegis-asp.com/`
- NHSN Reporting: `https://aegis-asp.com/nhsn-reporting/`
- HAI Detection: `https://aegis-asp.com/hai-detection/`
- ASP Alerts: `https://aegis-asp.com/asp-alerts/`
