#!/usr/bin/env python3
"""
Test Runner for Hokm Game Server
Provides easy access to different test categories
"""

import os
import sys
import subprocess
import argparse

def run_command(cmd, description):
    """Run a command and handle output"""
    print(f"\n{'='*60}")
    print(f"Running: {description}")
    print(f"Command: {cmd}")
    print('='*60)
    
    try:
        result = subprocess.run(cmd, shell=True, check=True, capture_output=False)
        print(f"✅ {description} completed successfully")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ {description} failed with exit code {e.returncode}")
        return False

def main():
    parser = argparse.ArgumentParser(description='Run Hokm Game Server Tests')
    parser.add_argument('category', nargs='?', default='all', 
                       help='Test category to run (default: all)')
    
    # Add test category options
    parser.add_argument('--list', action='store_true',
                       help='List available test categories')
    parser.add_argument('--verbose', '-v', action='store_true',
                       help='Run tests with verbose output')
    
    args = parser.parse_args()
    
    # Define test categories
    test_categories = {
        'all': {
            'cmd': 'python -m pytest',
            'description': 'All tests'
        },
        'core': {
            'cmd': 'python -m pytest -k "basic_game or game_completion or gameboard"',
            'description': 'Core game logic tests'
        },
        'network': {
            'cmd': 'python -m pytest -k "server or client or connection"',
            'description': 'Network and communication tests'
        },
        'reconnection': {
            'cmd': 'python -m pytest -k "reconnection or disconnect"',
            'description': 'Reconnection and disconnect handling tests'
        },
        'database': {
            'cmd': 'python -m pytest -k "postgresql or redis or database"',
            'description': 'Database integration tests'
        },
        'performance': {
            'cmd': 'python -m pytest -k "stress or load or performance"',
            'description': 'Performance and load tests'
        },
        'fixes': {
            'cmd': 'python -m pytest -k "fix"',
            'description': 'Bug fix verification tests'
        },
        'integration': {
            'cmd': 'python -m pytest -k "integration or e2e or comprehensive"',
            'description': 'Integration and end-to-end tests'
        }
    }
    
    # Quick test commands
    quick_tests = {
        'quick': {
            'cmd': 'python quick_test.py',
            'description': 'Quick functionality test'
        },
        'demo': {
            'cmd': 'python demo_reconnection.py',
            'description': 'Reconnection demo'
        }
    }
    
    if args.list:
        print("Available test categories:")
        print("\nMain test categories:")
        for name, info in test_categories.items():
            print(f"  {name:12} - {info['description']}")
        
        print("\nQuick tests:")
        for name, info in quick_tests.items():
            print(f"  {name:12} - {info['description']}")
        
        print("\nUsage examples:")
        print("  python test_runner.py                    # Run all tests")
        print("  python test_runner.py core               # Run core game tests")
        print("  python test_runner.py reconnection -v    # Run reconnection tests with verbose output")
        print("  python test_runner.py quick              # Run quick test")
        return
    
    # Change to tests directory
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    
    # Add verbose flag if requested
    verbose_flag = ' -v' if args.verbose else ''
    
    # Run the requested test category
    category = args.category.lower()
    
    if category in test_categories:
        cmd = test_categories[category]['cmd'] + verbose_flag
        description = test_categories[category]['description']
        success = run_command(cmd, description)
    elif category in quick_tests:
        cmd = quick_tests[category]['cmd']
        description = quick_tests[category]['description']
        success = run_command(cmd, description)
    else:
        print(f"❌ Unknown test category: {category}")
        print("Use --list to see available categories")
        sys.exit(1)
    
    if not success:
        sys.exit(1)
    
    print(f"\n🎉 Test execution completed!")

if __name__ == '__main__':
    main()
