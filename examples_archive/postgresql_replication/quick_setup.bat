@echo off
echo ===============================================
echo   Docker-Based Fault Tolerance Demo Setup
echo   PostgreSQL Streaming Replication Ready
echo ===============================================
echo.

cd /d "%~dp0"

REM Check if Docker is running
docker version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Docker is not running. Please start Docker Desktop first.
    echo Press any key to exit...
    pause >nul
    exit /b 1
)

echo [1/5] Docker is running...

REM Stop any existing containers
echo [2/5] Stopping existing containers...
docker-compose down 2>nul

REM Build and start the replication setup
echo [3/5] Starting PostgreSQL replication containers...
docker-compose up -d

REM Wait for services to be ready
echo [4/5] Waiting for services to start (this may take 30 seconds)...
timeout /t 30 /nobreak >nul

REM Verify services are running
echo [5/5] Verifying services...
docker-compose ps

echo.
echo ===============================================
echo            SETUP COMPLETE!
echo ===============================================
echo.
echo Services running:
echo   Primary DB:   localhost:5432
echo   Standby DB:   localhost:5433  
echo   Redis:        localhost:6379
echo   Load Balancer: localhost:8080
echo.
echo ✅ Ready for demonstration!
echo.
echo Next steps:
echo   1. Test database replication: python test_failover.py
echo   2. Run fault tolerance demo:  python fault_tolerance_demo.py
echo.
echo Press any key to continue...
pause >nul
