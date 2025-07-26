#!/usr/bin/env python3
"""
Database Deployment Setup Validation
Validates that all components are properly configured and ready for deployment

Features:
- Configuration validation
- Dependency checking  
- Environment verification
- Integration testing
"""

import asyncio
import logging
import sys
import os
import json
import importlib.util
from pathlib import Path
from typing import Dict, List, Any, Optional

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s'
)
logger = logging.getLogger(__name__)


class DeploymentValidator:
    """
    Validates database deployment automation setup
    """
    
    def __init__(self):
        self.project_root = Path(__file__).parent.parent
        self.database_dir = self.project_root / "database"
        self.validation_results = []
        
    async def validate_all(self) -> Dict[str, Any]:
        """
        Run all validation checks
        """
        validation_summary = {
            'timestamp': None,
            'overall_status': 'unknown',
            'checks': [],
            'summary': {
                'total': 0,
                'passed': 0,
                'failed': 0,
                'warnings': 0
            }
        }
        
        # List of validation checks
        checks = [
            ('Project Structure', self.validate_project_structure),
            ('Python Dependencies', self.validate_dependencies),
            ('Configuration Files', self.validate_configurations),
            ('Database Scripts', self.validate_database_scripts),
            ('CI/CD Pipeline', self.validate_cicd_pipeline),
            ('Environment Variables', self.validate_environment_variables),
            ('Script Permissions', self.validate_script_permissions),
            ('Import Dependencies', self.validate_imports)
        ]
        
        logger.info("Starting deployment validation...")
        
        for check_name, check_func in checks:
            try:
                logger.info(f"Running check: {check_name}")
                result = await check_func()
                
                check_result = {
                    'name': check_name,
                    'status': 'passed' if result.get('success', False) else 'failed',
                    'details': result,
                    'warnings': result.get('warnings', []),
                    'errors': result.get('errors', [])
                }
                
                validation_summary['checks'].append(check_result)
                validation_summary['summary']['total'] += 1
                
                if check_result['status'] == 'passed':
                    validation_summary['summary']['passed'] += 1
                    if check_result['warnings']:
                        validation_summary['summary']['warnings'] += 1
                        logger.warning(f"✓ {check_name} passed with warnings")
                    else:
                        logger.info(f"✓ {check_name} passed")
                else:
                    validation_summary['summary']['failed'] += 1
                    logger.error(f"✗ {check_name} failed")
                    
            except Exception as e:
                check_result = {
                    'name': check_name,
                    'status': 'failed',
                    'details': {'success': False, 'error': str(e)},
                    'warnings': [],
                    'errors': [str(e)]
                }
                
                validation_summary['checks'].append(check_result)
                validation_summary['summary']['total'] += 1
                validation_summary['summary']['failed'] += 1
                
                logger.error(f"✗ {check_name} failed with exception: {e}")
        
        # Determine overall status
        if validation_summary['summary']['failed'] == 0:
            validation_summary['overall_status'] = 'passed'
        else:
            validation_summary['overall_status'] = 'failed'
            
        validation_summary['timestamp'] = asyncio.get_event_loop().time()
        
        return validation_summary
    
    async def validate_project_structure(self) -> Dict[str, Any]:
        """
        Validate project directory structure
        """
        required_files = [
            'database/deploy.py',
            'database/seed_data.py', 
            'database/smoke_tests.py',
            'database/rollback.py',
            'database/README.md',
            'database/config/development.json',
            'database/config/testing.json',
            'database/config/staging.json',
            'database/config/production.json',
            '.github/workflows/database.yml',
            'backend/database/models.py',
            'backend/database/config.py',
            'requirements.txt'
        ]
        
        required_directories = [
            'database',
            'database/config',
            'database/backups',
            'backend/database',
            '.github/workflows'
        ]
        
        missing_files = []
        missing_directories = []
        
        # Check files
        for file_path in required_files:
            full_path = self.project_root / file_path
            if not full_path.exists():
                missing_files.append(file_path)
        
        # Check directories
        for dir_path in required_directories:
            full_path = self.project_root / dir_path
            if not full_path.exists():
                missing_directories.append(dir_path)
        
        return {
            'success': len(missing_files) == 0 and len(missing_directories) == 0,
            'missing_files': missing_files,
            'missing_directories': missing_directories,
            'checked_files': len(required_files),
            'checked_directories': len(required_directories)
        }
    
    async def validate_dependencies(self) -> Dict[str, Any]:
        """
        Validate Python dependencies
        """
        required_packages = [
            'asyncpg',
            'sqlalchemy',
            'alembic',
            'pytest',
            'psutil',
            'aiofiles'
        ]
        
        missing_packages = []
        available_packages = []
        
        for package in required_packages:
            try:
                spec = importlib.util.find_spec(package)
                if spec is None:
                    missing_packages.append(package)
                else:
                    available_packages.append(package)
            except Exception:
                missing_packages.append(package)
        
        # Check requirements.txt exists
        requirements_file = self.project_root / 'requirements.txt'
        has_requirements_file = requirements_file.exists()
        
        return {
            'success': len(missing_packages) == 0,
            'missing_packages': missing_packages,
            'available_packages': available_packages,
            'has_requirements_file': has_requirements_file,
            'warnings': ['Some packages may not be installed'] if missing_packages else []
        }
    
    async def validate_configurations(self) -> Dict[str, Any]:
        """
        Validate configuration files
        """
        config_files = [
            'development.json',
            'testing.json', 
            'staging.json',
            'production.json'
        ]
        
        config_dir = self.database_dir / 'config'
        validation_results = {}
        errors = []
        warnings = []
        
        for config_file in config_files:
            config_path = config_dir / config_file
            
            if not config_path.exists():
                errors.append(f"Missing configuration file: {config_file}")
                continue
                
            try:
                with open(config_path, 'r') as f:
                    config_data = json.load(f)
                
                # Validate required sections
                required_sections = ['environment', 'database', 'backup', 'deployment']
                missing_sections = [section for section in required_sections 
                                  if section not in config_data]
                
                if missing_sections:
                    errors.append(f"{config_file}: Missing sections: {missing_sections}")
                
                # Check for environment variables in values
                env_vars = []
                def find_env_vars(obj, prefix=""):
                    if isinstance(obj, dict):
                        for key, value in obj.items():
                            find_env_vars(value, f"{prefix}.{key}" if prefix else key)
                    elif isinstance(obj, str) and obj.startswith("${") and obj.endswith("}"):
                        env_vars.append((prefix, obj))
                
                find_env_vars(config_data)
                
                validation_results[config_file] = {
                    'valid': len(missing_sections) == 0,
                    'missing_sections': missing_sections,
                    'environment_variables': env_vars
                }
                
            except json.JSONDecodeError as e:
                errors.append(f"{config_file}: Invalid JSON - {e}")
            except Exception as e:
                errors.append(f"{config_file}: Error reading file - {e}")
        
        return {
            'success': len(errors) == 0,
            'errors': errors,
            'warnings': warnings,
            'config_files': validation_results
        }
    
    async def validate_database_scripts(self) -> Dict[str, Any]:
        """
        Validate database scripts syntax and imports
        """
        script_files = [
            'deploy.py',
            'seed_data.py',
            'smoke_tests.py', 
            'rollback.py'
        ]
        
        validation_results = {}
        errors = []
        warnings = []
        
        for script_file in script_files:
            script_path = self.database_dir / script_file
            
            if not script_path.exists():
                errors.append(f"Missing script: {script_file}")
                continue
            
            try:
                # Check if file is executable
                is_executable = os.access(script_path, os.X_OK)
                if not is_executable:
                    warnings.append(f"{script_file} is not executable")
                
                # Try to compile the script
                with open(script_path, 'r') as f:
                    source_code = f.read()
                
                compile(source_code, str(script_path), 'exec')
                
                validation_results[script_file] = {
                    'syntax_valid': True,
                    'executable': is_executable,
                    'size_bytes': len(source_code)
                }
                
            except SyntaxError as e:
                errors.append(f"{script_file}: Syntax error - {e}")
                validation_results[script_file] = {
                    'syntax_valid': False,
                    'executable': False,
                    'error': str(e)
                }
            except Exception as e:
                errors.append(f"{script_file}: Error reading file - {e}")
        
        return {
            'success': len(errors) == 0,
            'errors': errors,
            'warnings': warnings,
            'scripts': validation_results
        }
    
    async def validate_cicd_pipeline(self) -> Dict[str, Any]:
        """
        Validate CI/CD pipeline configuration
        """
        pipeline_file = self.project_root / '.github' / 'workflows' / 'database.yml'
        
        if not pipeline_file.exists():
            return {
                'success': False,
                'errors': ['CI/CD pipeline file missing'],
                'warnings': []
            }
        
        try:
            with open(pipeline_file, 'r') as f:
                pipeline_content = f.read()
            
            # Basic validation - check for required sections
            required_sections = [
                'name:', 
                'on:', 
                'jobs:',
                'validate:',
                'deploy-staging:',
                'deploy-production:'
            ]
            
            missing_sections = []
            for section in required_sections:
                if section not in pipeline_content:
                    missing_sections.append(section)
            
            return {
                'success': len(missing_sections) == 0,
                'missing_sections': missing_sections,
                'file_size': len(pipeline_content),
                'warnings': ['Pipeline syntax not fully validated'] if missing_sections else []
            }
            
        except Exception as e:
            return {
                'success': False,
                'errors': [f"Error reading pipeline file: {e}"],
                'warnings': []
            }
    
    async def validate_environment_variables(self) -> Dict[str, Any]:
        """
        Validate environment variable setup
        """
        # Common environment variables that should be set
        common_env_vars = [
            'DB_HOST',
            'DB_PORT', 
            'DB_NAME',
            'DB_USER'
        ]
        
        # Environment-specific variables
        env_specific_vars = [
            'DB_PASSWORD_DEV',
            'DB_PASSWORD_TEST', 
            'DB_PASSWORD_STAGING',
            'DB_PASSWORD_PRODUCTION'
        ]
        
        missing_vars = []
        present_vars = []
        warnings = []
        
        # Check common variables
        for var in common_env_vars:
            if os.getenv(var):
                present_vars.append(var)
            else:
                warnings.append(f"Environment variable {var} not set (using defaults)")
        
        # Check environment-specific variables
        for var in env_specific_vars:
            if os.getenv(var):
                present_vars.append(var)
            else:
                missing_vars.append(var)
        
        # Check for .env files
        env_files = [
            '.env',
            '.env.database',
            '.env.example'
        ]
        
        existing_env_files = []
        for env_file in env_files:
            env_path = self.project_root / env_file
            if env_path.exists():
                existing_env_files.append(env_file)
        
        return {
            'success': True,  # Not critical for basic validation
            'missing_variables': missing_vars,
            'present_variables': present_vars,
            'existing_env_files': existing_env_files,
            'warnings': warnings + [f"Missing environment variables: {missing_vars}"] if missing_vars else warnings
        }
    
    async def validate_script_permissions(self) -> Dict[str, Any]:
        """
        Validate script file permissions
        """
        script_files = [
            'deploy.py',
            'seed_data.py',
            'smoke_tests.py',
            'rollback.py'
        ]
        
        permission_issues = []
        correct_permissions = []
        
        for script_file in script_files:
            script_path = self.database_dir / script_file
            
            if script_path.exists():
                is_executable = os.access(script_path, os.X_OK)
                is_readable = os.access(script_path, os.R_OK)
                
                if is_executable and is_readable:
                    correct_permissions.append(script_file)
                else:
                    permission_issues.append({
                        'file': script_file,
                        'executable': is_executable,
                        'readable': is_readable
                    })
        
        return {
            'success': len(permission_issues) == 0,
            'permission_issues': permission_issues,
            'correct_permissions': correct_permissions,
            'warnings': [f"Permission issues with: {[issue['file'] for issue in permission_issues]}"] if permission_issues else []
        }
    
    async def validate_imports(self) -> Dict[str, Any]:
        """
        Validate that scripts can import required modules
        """
        import_tests = [
            ('asyncio', 'Python async support'),
            ('sqlalchemy', 'Database ORM'),
            ('asyncpg', 'PostgreSQL async driver'),
            ('pathlib.Path', 'Path handling'),
            ('json', 'JSON processing'),
            ('logging', 'Logging support'),
            ('subprocess', 'Process execution'),
            ('datetime.datetime', 'Date/time handling')
        ]
        
        successful_imports = []
        failed_imports = []
        
        for module_name, description in import_tests:
            try:
                # Try to import the module
                if '.' in module_name:
                    module_parts = module_name.split('.')
                    module = __import__(module_parts[0])
                    for part in module_parts[1:]:
                        module = getattr(module, part)
                else:
                    __import__(module_name)
                
                successful_imports.append({
                    'module': module_name,
                    'description': description
                })
                
            except ImportError as e:
                failed_imports.append({
                    'module': module_name,
                    'description': description,
                    'error': str(e)
                })
            except Exception as e:
                failed_imports.append({
                    'module': module_name,
                    'description': description,
                    'error': f"Unexpected error: {e}"
                })
        
        return {
            'success': len(failed_imports) == 0,
            'successful_imports': successful_imports,
            'failed_imports': failed_imports,
            'errors': [f"Failed to import {imp['module']}: {imp['error']}" for imp in failed_imports]
        }


async def main():
    """
    Main entry point for validation
    """
    validator = DeploymentValidator()
    
    try:
        logger.info("=== Database Deployment Validation ===")
        results = await validator.validate_all()
        
        # Print summary
        print("\n" + "="*60)
        print("VALIDATION SUMMARY")
        print("="*60)
        print(f"Overall Status: {results['overall_status'].upper()}")
        print(f"Total Checks: {results['summary']['total']}")
        print(f"Passed: {results['summary']['passed']}")
        print(f"Failed: {results['summary']['failed']}")
        print(f"Warnings: {results['summary']['warnings']}")
        print()
        
        # Print details for failed checks
        failed_checks = [check for check in results['checks'] if check['status'] == 'failed']
        if failed_checks:
            print("FAILED CHECKS:")
            print("-" * 40)
            for check in failed_checks:
                print(f"✗ {check['name']}")
                for error in check['errors']:
                    print(f"  - {error}")
            print()
        
        # Print warnings
        warning_checks = [check for check in results['checks'] if check['warnings']]
        if warning_checks:
            print("WARNINGS:")
            print("-" * 40)
            for check in warning_checks:
                print(f"⚠ {check['name']}")
                for warning in check['warnings']:
                    print(f"  - {warning}")
            print()
        
        # Success message
        if results['overall_status'] == 'passed':
            print("🎉 All validation checks passed!")
            print("Database deployment automation is ready to use.")
        else:
            print("❌ Validation failed!")
            print("Please fix the issues above before proceeding with deployment.")
            sys.exit(1)
        
    except Exception as e:
        logger.error(f"Validation failed with exception: {e}")
        sys.exit(1)


if __name__ == '__main__':
    asyncio.run(main())
