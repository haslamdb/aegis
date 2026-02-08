#!/bin/bash
# AEGIS Development Environment Setup Script
# Sets up Docker Compose environment for local Flask + Django development

set -e  # Exit on error

echo "=========================================="
echo "AEGIS Development Environment Setup"
echo "=========================================="

# Check prerequisites
command -v docker >/dev/null 2>&1 || { echo "Error: Docker not installed. Please install Docker first."; exit 1; }
command -v docker-compose >/dev/null 2>&1 || { echo "Error: Docker Compose not installed. Please install Docker Compose first."; exit 1; }

# Get project root directory (one level up from scripts/)
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

echo "Project root: $PROJECT_ROOT"

# Copy .env template if .env doesn't exist
if [ ! -f .env ]; then
    echo "Creating .env from template..."
    cp .env.template .env

    # Generate secure passwords
    POSTGRES_PASSWORD=$(openssl rand -base64 32)
    REDIS_PASSWORD=$(openssl rand -base64 32)
    DJANGO_SECRET_KEY=$(openssl rand -base64 64)
    FLOWER_PASSWORD=$(openssl rand -base64 16)

    # Update .env with generated passwords
    sed -i.bak "s|POSTGRES_PASSWORD=your_secure_password_here|POSTGRES_PASSWORD=$POSTGRES_PASSWORD|g" .env
    sed -i.bak "s|REDIS_PASSWORD=your_redis_password_here|REDIS_PASSWORD=$REDIS_PASSWORD|g" .env
    sed -i.bak "s|DJANGO_SECRET_KEY=your_django_secret_key_here_minimum_50_characters_long|DJANGO_SECRET_KEY=$DJANGO_SECRET_KEY|g" .env
    sed -i.bak "s|FLOWER_PASSWORD=your_flower_password_here|FLOWER_PASSWORD=$FLOWER_PASSWORD|g" .env
    rm .env.bak

    echo "✓ Created .env with generated passwords"
else
    echo "✓ .env file already exists"
fi

# Create necessary directories
echo "Creating directories..."
mkdir -p docker/nginx/ssl
mkdir -p aegis-django  # Will be populated by Django Architect
mkdir -p data/postgres
mkdir -p data/redis
mkdir -p logs/celery

echo "✓ Directories created"

# Build Docker images
echo "Building Docker images..."
docker-compose build

echo "✓ Docker images built"

# Start services
echo "Starting services..."
docker-compose up -d postgres redis hapi-fhir

echo "Waiting for PostgreSQL to be ready..."
until docker-compose exec -T postgres pg_isready -U aegis_user -d aegis; do
    sleep 2
done
echo "✓ PostgreSQL is ready"

echo "Waiting for Redis to be ready..."
until docker-compose exec -T redis redis-cli ping | grep -q PONG; do
    sleep 2
done
echo "✓ Redis is ready"

echo ""
echo "=========================================="
echo "Development Environment Setup Complete!"
echo "=========================================="
echo ""
echo "Services available:"
echo "  - PostgreSQL:  localhost:5432"
echo "  - Redis:       localhost:6379"
echo "  - HAPI FHIR:   http://localhost:8081"
echo ""
echo "Next steps:"
echo "  1. Wait for Django Architect to create aegis-django/ structure"
echo "  2. Start Flask: docker-compose up -d flask"
echo "  3. Start Django: docker-compose up -d django celery celery-beat"
echo "  4. Start Nginx: docker-compose up -d nginx"
echo "  5. Access application: http://localhost:8080"
echo "  6. Access Flower (Celery monitoring): http://localhost:5555"
echo ""
echo "View logs:"
echo "  docker-compose logs -f flask"
echo "  docker-compose logs -f django"
echo "  docker-compose logs -f celery"
echo ""
