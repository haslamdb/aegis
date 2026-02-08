#!/bin/bash
# AEGIS Module Cutover Script
# Helps migrate individual modules from Flask to Django by updating Nginx routing

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

NGINX_CONF="/home/david/projects/aegis/docker/nginx/conf.d/aegis.conf"

# Function to list available modules
list_modules() {
    echo "Available AEGIS modules:"
    echo "  1. dosing-verification"
    echo "  2. action-analytics"
    echo "  3. mdro-surveillance"
    echo "  4. drug-bug-mismatch"
    echo "  5. hai-detection"
    echo "  6. guideline-adherence"
    echo "  7. surgical-prophylaxis"
    echo "  8. abx-approvals"
    echo "  9. nhsn-reporting"
    echo " 10. outbreak-detection"
    echo " 11. abx-indications"
}

# Function to check current routing for a module
check_routing() {
    local module=$1
    echo -e "${YELLOW}Checking routing for /$module/${NC}"

    if grep -q "location /$module/" "$NGINX_CONF"; then
        if grep -A 5 "location /$module/" "$NGINX_CONF" | grep -q "django_backend"; then
            echo -e "${GREEN}✓ Currently routed to Django${NC}"
        elif grep -A 5 "location /$module/" "$NGINX_CONF" | grep -q "flask_backend"; then
            echo -e "${YELLOW}→ Currently routed to Flask${NC}"
        else
            echo -e "${RED}? Routing unclear${NC}"
        fi
    else
        echo -e "${YELLOW}→ Using default routing (Flask)${NC}"
    fi
}

# Function to cutover module to Django
cutover_to_django() {
    local module=$1
    echo -e "${YELLOW}Cutting over /$module/ to Django...${NC}"

    # Check if location block exists
    if grep -q "location /$module/" "$NGINX_CONF"; then
        # Uncomment if commented
        sed -i "s|# location /$module/|location /$module/|g" "$NGINX_CONF"
        # Change proxy_pass to django_backend
        sed -i "/location \/$module\//,/}/s|proxy_pass http://flask_backend|proxy_pass http://django_backend|g" "$NGINX_CONF"
    else
        # Add new location block
        # Find the line with "# Add more Django modules here" and insert before it
        local insert_line=$(grep -n "# Add more Django modules here" "$NGINX_CONF" | cut -d: -f1)
        if [ -n "$insert_line" ]; then
            sed -i "${insert_line}i\\
    # Module: $module (migrated to Django)\\
    location /$module/ {\\
        limit_req zone=aegis_general burst=20 nodelay;\\
        proxy_pass http://django_backend;\\
        proxy_set_header Host \$host;\\
        proxy_set_header X-Real-IP \$remote_addr;\\
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;\\
        proxy_set_header X-Forwarded-Proto \$scheme;\\
        proxy_redirect off;\\
    }\\
\\
" "$NGINX_CONF"
        fi
    fi

    echo -e "${GREEN}✓ Nginx config updated${NC}"
}

# Function to rollback module to Flask
rollback_to_flask() {
    local module=$1
    echo -e "${YELLOW}Rolling back /$module/ to Flask...${NC}"

    if grep -q "location /$module/" "$NGINX_CONF"; then
        # Change proxy_pass to flask_backend
        sed -i "/location \/$module\//,/}/s|proxy_pass http://django_backend|proxy_pass http://flask_backend|g" "$NGINX_CONF"
        echo -e "${GREEN}✓ Nginx config updated${NC}"
    else
        echo -e "${YELLOW}No explicit routing found for /$module/ - already using default Flask routing${NC}"
    fi
}

# Function to reload Nginx
reload_nginx() {
    echo -e "${YELLOW}Reloading Nginx...${NC}"

    # Check if running in Docker Compose
    if docker-compose ps nginx | grep -q Up; then
        # Test config first
        docker-compose exec nginx nginx -t
        if [ $? -eq 0 ]; then
            docker-compose exec nginx nginx -s reload
            echo -e "${GREEN}✓ Nginx reloaded successfully${NC}"
        else
            echo -e "${RED}✗ Nginx config test failed - NOT reloading${NC}"
            exit 1
        fi
    # Check if running as systemd service
    elif systemctl is-active --quiet nginx; then
        sudo nginx -t
        if [ $? -eq 0 ]; then
            sudo systemctl reload nginx
            echo -e "${GREEN}✓ Nginx reloaded successfully${NC}"
        else
            echo -e "${RED}✗ Nginx config test failed - NOT reloading${NC}"
            exit 1
        fi
    else
        echo -e "${YELLOW}Warning: Nginx not running or not found${NC}"
        echo "Please reload manually after starting Nginx"
    fi
}

# Main script
echo "=========================================="
echo "AEGIS Module Cutover Tool"
echo "=========================================="
echo ""

if [ $# -eq 0 ]; then
    list_modules
    echo ""
    echo "Usage:"
    echo "  $0 <module-name> cutover   - Route module to Django"
    echo "  $0 <module-name> rollback  - Route module back to Flask"
    echo "  $0 <module-name> status    - Check current routing"
    echo ""
    echo "Example:"
    echo "  $0 dosing-verification cutover"
    echo "  $0 dosing-verification rollback"
    exit 1
fi

MODULE=$1
ACTION=${2:-status}

case $ACTION in
    status)
        check_routing "$MODULE"
        ;;
    cutover)
        check_routing "$MODULE"
        echo ""
        cutover_to_django "$MODULE"
        echo ""
        echo -e "${YELLOW}Ready to reload Nginx? (y/n)${NC}"
        read -r response
        if [[ "$response" =~ ^[Yy]$ ]]; then
            reload_nginx
            echo ""
            echo -e "${GREEN}✓ Cutover complete!${NC}"
            echo "Monitor logs for any issues:"
            echo "  docker-compose logs -f nginx django"
        else
            echo "Skipped reload. Run this to apply changes:"
            echo "  docker-compose exec nginx nginx -s reload"
        fi
        ;;
    rollback)
        check_routing "$MODULE"
        echo ""
        rollback_to_flask "$MODULE"
        echo ""
        echo -e "${YELLOW}Ready to reload Nginx? (y/n)${NC}"
        read -r response
        if [[ "$response" =~ ^[Yy]$ ]]; then
            reload_nginx
            echo ""
            echo -e "${GREEN}✓ Rollback complete!${NC}"
            echo "Module /$MODULE/ is now served by Flask"
        else
            echo "Skipped reload. Run this to apply changes:"
            echo "  docker-compose exec nginx nginx -s reload"
        fi
        ;;
    *)
        echo -e "${RED}Unknown action: $ACTION${NC}"
        echo "Valid actions: cutover, rollback, status"
        exit 1
        ;;
esac
