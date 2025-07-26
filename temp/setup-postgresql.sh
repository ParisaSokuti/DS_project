#!/bin/bash
# Setup script for PostgreSQL environment

set -e

echo "🐘 Setting up PostgreSQL environment for Hokm Game Server"
echo "========================================================"

# Create data directories
echo "Creating data directories..."
mkdir -p data/postgres
mkdir -p data/postgres_replica
mkdir -p data/redis
mkdir -p data/backups
mkdir -p logs

# Set appropriate permissions
chmod 700 data/postgres
chmod 700 data/postgres_replica
chmod 755 data/redis
chmod 755 data/backups
chmod 755 logs

# Create .env file if it doesn't exist
if [ ! -f .env ]; then
    echo "Creating .env file from template..."
    cp .env.example .env
    echo "⚠️  Please review and update the .env file with your desired settings"
else
    echo ".env file already exists"
fi

# Generate secure passwords if using defaults
if grep -q "hokm_secure_2024!" .env; then
    echo "⚠️  Warning: Using default passwords. Please update them in .env file for production!"
fi

echo ""
echo "✅ Setup completed successfully!"
echo ""
echo "Next steps:"
echo "1. Review and update the .env file with your desired settings"
echo "2. Start the services: docker-compose up -d"
echo "3. Run the test suite: python test_postgresql_integration.py"
echo ""
echo "Services will be available at:"
echo "- PostgreSQL Primary: localhost:5432"
echo "- PostgreSQL Replica: localhost:5433"
echo "- pgBouncer: localhost:6432"
echo "- Redis: localhost:6379"
echo "- pgAdmin: http://localhost:5050"
echo "- Grafana: http://localhost:3000"
echo "- Prometheus: http://localhost:9090"
