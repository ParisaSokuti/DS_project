@echo off
REM PostgreSQL Streaming Replication Setup for Windows
REM Demonstrates fault tolerance for Hokm Game

echo 🏗️  Setting up PostgreSQL Streaming Replication for Fault Tolerance Demo
echo ==================================================================

REM Variables (adjust paths according to your PostgreSQL installation)
set PRIMARY_DATA_DIR=C:\Program Files\PostgreSQL\13\data
set STANDBY_DATA_DIR=C:\PostgreSQL\standby_data
set REPLICATION_USER=replicator
set REPLICATION_SLOT=standby_slot_1
set PGPASSWORD=repl_password123

echo 📋 Step 1: Creating replication user on primary server
psql -U postgres -c "CREATE USER %REPLICATION_USER% WITH REPLICATION ENCRYPTED PASSWORD '%PGPASSWORD%';"

echo 📋 Step 2: Creating replication slot on primary server
psql -U postgres -c "SELECT pg_create_physical_replication_slot('%REPLICATION_SLOT%');"

echo 📋 Step 3: Creating directory for standby server
if not exist "%STANDBY_DATA_DIR%" mkdir "%STANDBY_DATA_DIR%"

echo 📋 Step 4: Creating base backup for standby server
pg_basebackup -h localhost -D "%STANDBY_DATA_DIR%" -U %REPLICATION_USER% -v -P

echo 📋 Step 5: Setting up standby.signal file (PostgreSQL 12+)
echo. > "%STANDBY_DATA_DIR%\standby.signal"

echo 📋 Step 6: Creating recovery configuration
echo primary_conninfo = 'host=127.0.0.1 port=5432 user=%REPLICATION_USER% password=%PGPASSWORD% application_name=standby1' > "%STANDBY_DATA_DIR%\postgresql.auto.conf"
echo primary_slot_name = '%REPLICATION_SLOT%' >> "%STANDBY_DATA_DIR%\postgresql.auto.conf"

echo 📋 Step 7: Copy standby configuration
copy "standby\postgresql.conf" "%STANDBY_DATA_DIR%\postgresql.conf"
copy "standby\pg_hba.conf" "%STANDBY_DATA_DIR%\pg_hba.conf"

echo ✅ PostgreSQL Streaming Replication setup complete!
echo.
echo 🚀 To start the servers:
echo 1. Primary:  net start postgresql-x64-13
echo 2. Standby:  pg_ctl start -D "%STANDBY_DATA_DIR%"
echo.
echo 📊 To monitor replication:
echo    psql -U postgres -c "SELECT * FROM pg_stat_replication;"
echo.
echo 🔧 To promote standby to primary:
echo    pg_ctl promote -D "%STANDBY_DATA_DIR%"

pause
