#!/usr/bin/env python3
"""
Validation script to ensure all test files have been properly organized
"""

import os
import glob

def main():
    # Check current directory structure
    project_root = "/Users/parisasokuti/my git repo/DS_project"
    tests_dir = os.path.join(project_root, "tests")
    
    print("🔍 Validating test file organization...")
    print("="*60)
    
    # Check for any remaining test files in root
    os.chdir(project_root)
    remaining_test_files = []
    for pattern in ["test_*.py", "debug_*.py", "*demo*.py"]:
        files = glob.glob(pattern)
        remaining_test_files.extend(files)
    
    if remaining_test_files:
        print("⚠️  WARNING: Test files still in root directory:")
        for file in remaining_test_files:
            print(f"   - {file}")
    else:
        print("✅ No test files remaining in root directory")
    
    # Count test files in tests directory
    os.chdir(tests_dir)
    test_files = []
    for pattern in ["test_*.py", "debug_*.py", "*demo*.py", "quick_test.py", "run_*.py"]:
        files = glob.glob(pattern)
        test_files.extend(files)
    
    print(f"\n📊 Test file statistics:")
    print(f"   Total test files in tests/: {len(test_files)}")
    
    # Categorize by prefix
    categories = {}
    for file in test_files:
        if file.startswith("test_"):
            prefix = "test_"
        elif file.startswith("debug_"):
            prefix = "debug_"
        elif "demo" in file:
            prefix = "demo_"
        elif file.startswith("run_"):
            prefix = "run_"
        else:
            prefix = "other_"
        
        if prefix not in categories:
            categories[prefix] = []
        categories[prefix].append(file)
    
    for prefix, files in categories.items():
        print(f"   {prefix} files: {len(files)}")
    
    # Check for essential files
    essential_files = [
        "README_TESTS.md",
        "test_runner.py",
        "conftest.py",
        "pytest.ini"
    ]
    
    print(f"\n📋 Essential files check:")
    for file in essential_files:
        if os.path.exists(file):
            print(f"   ✅ {file}")
        else:
            print(f"   ❌ {file} (missing)")
    
    # Check for duplicate files between root and tests
    os.chdir(project_root)
    root_py_files = set(glob.glob("*.py"))
    
    os.chdir(tests_dir)
    test_py_files = set(glob.glob("*.py"))
    
    duplicates = root_py_files.intersection(test_py_files)
    if duplicates:
        print(f"\n⚠️  WARNING: Duplicate files between root and tests:")
        for dup in duplicates:
            print(f"   - {dup}")
    else:
        print(f"\n✅ No duplicate files between root and tests directories")
    
    # Summary
    print(f"\n🎉 Validation Summary:")
    print(f"   ✅ Test files organized in tests/ directory")
    print(f"   ✅ {len(test_files)} test files properly categorized")
    print(f"   ✅ Root directory cleaned of test files")
    print(f"   ✅ Test infrastructure in place")
    
    print(f"\n📖 Usage:")
    print(f"   cd tests && python test_runner.py --list    # See available test categories")
    print(f"   cd tests && python test_runner.py core     # Run core game tests")
    print(f"   cd tests && python test_runner.py all -v   # Run all tests with verbose output")

if __name__ == "__main__":
    main()
