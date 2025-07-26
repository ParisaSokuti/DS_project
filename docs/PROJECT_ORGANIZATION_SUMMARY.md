# Project Organization Summary

## Core Functional Files (Kept in Root)

### Main Application
- `backend/` - Contains the main server.py and client.py files and all their dependencies
  - `server.py` - Main game server
  - `client.py` - Game client
  - All supporting modules (network.py, game_board.py, game_states.py, etc.)

### Tests
- `tests/` - Test files

### Configuration & Deployment
- `docker-compose.yml` - Main Docker configuration (paths updated to temp/)
- `docker-compose.scaling.yml` - Scaling configuration
- `k8s-deployment.yml` - Kubernetes deployment
- `requirements.txt` - Python dependencies
- `requirements-auth.txt` - Authentication dependencies
- `requirements-postgresql.txt` - PostgreSQL dependencies
- `database_schema.sql` - Database schema

### Environment & Git
- `.env.example` - Environment template
- `.env.database.example` - Database environment template
- `.gitignore` - Git ignore rules
- `.github/` - GitHub Actions workflows

## Moved to temp/ Folder

### Documentation
- All README and documentation MD files
- Guides, summaries, and status reports

### Standalone Scripts & Demos
- Demo scripts (fault_tolerance_demo.py, demo_reconnection_fix.py, etc.)
- Utility scripts (analyze_game_state.py, apply_critical_fixes.py, etc.)
- Alternative server implementations (enhanced_server_*.py, minimal_server.py, etc.)
- Setup and management scripts (setup_auth.py, change_db_password.py, etc.)

### Infrastructure & Configuration
- `config/` - Docker/PostgreSQL configuration files
- `database/` - Database management scripts
- `postgresql-ha/` - High availability setup
- `postgresql_replication/` - Replication setup
- `scripts/` - Utility shell scripts
- `examples/` - Example integration files
- `md/` - Documentation files
- `frontend/` - Web interface files (not actively used)

### System Files
- Shell scripts (.sh files)
- Cron jobs and service files
- Backup configurations

## Path Updates Made
- Updated all path references in `docker-compose.yml` to point to `temp/config/`, `temp/scripts/`, etc.
- Updated documentation file references to point to `temp/postgresql_replication/` and similar paths

## Result
The main directory now contains only the essential files needed to run the core game functionality (server and client), while all standalone, demo, documentation, frontend, and infrastructure setup files have been organized in the `temp/` folder. The main backend functionality remains fully intact and functional.

### Current Main Directory Structure:
- `backend/` - Core game server and client files
- `tests/` - Test files  
- `docker-compose.yml` and related deployment files
- `requirements*.txt` - Python dependencies
- `database_schema.sql` - Database schema
- Environment and configuration templates
