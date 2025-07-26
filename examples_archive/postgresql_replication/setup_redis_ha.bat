@echo off
echo ===============================================
echo   Redis Master-Replica with Sentinel Setup
echo   High Availability for Hokm Game System
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

echo [1/6] Docker is running...

REM Stop any existing containers
echo [2/6] Stopping existing containers...
docker-compose -f docker-compose-redis-ha.yml down 2>nul

REM Remove old volumes if they exist (for clean start)
set /p clean_volumes="Clean start? Remove existing data volumes? (y/n): "
if /i "%clean_volumes%"=="y" (
    echo [2.5/6] Removing old volumes for clean start...
    docker volume rm postgresql_replication_redis_master_data 2>nul
    docker volume rm postgresql_replication_redis_replica_data 2>nul
    echo   ✅ Old Redis volumes removed
)

REM Pull required images
echo [3/6] Pulling required Docker images...
docker pull postgres:13
docker pull redis:7-alpine
docker pull nginx:alpine

REM Start the Redis HA setup
echo [4/6] Starting Redis Master-Replica with Sentinel...
docker-compose -f docker-compose-redis-ha.yml up -d

REM Wait for services to be ready
echo [5/6] Waiting for services to start (45 seconds)...
timeout /t 45 /nobreak >nul

REM Verify services are running
echo [6/6] Verifying services...
docker-compose -f docker-compose-redis-ha.yml ps

echo.
echo ===============================================
echo            REDIS HA SETUP COMPLETE!
echo ===============================================
echo.
echo Services running:
echo   PostgreSQL Primary:  localhost:5432
echo   PostgreSQL Standby:  localhost:5433  
echo   Redis Master:        localhost:6379
echo   Redis Replica:       localhost:6380
echo   Redis Sentinel 1:    localhost:26379
echo   Redis Sentinel 2:    localhost:26380
echo   Redis Sentinel 3:    localhost:26381
echo   Load Balancer:       localhost:8080
echo.
echo Redis Configuration:
echo   Master Name:         hokm-master
echo   Password:            redis_game_password123
echo   Failover Quorum:     2 sentinels
echo   Down Timeout:        5 seconds
echo.
echo ✅ High Availability Features:
echo   • Automatic Redis failover via Sentinel
echo   • PostgreSQL streaming replication
echo   • Load balancer with health checks
echo   • Game session persistence
echo.
echo Next steps:
echo   1. Test Redis HA:     python test_redis_ha.py
echo   2. Test fault tolerance: python fault_tolerance_demo_simple.py
echo   3. Start game server: python ..\backend\server.py
echo.
echo Press any key to continue...
pause >nul
