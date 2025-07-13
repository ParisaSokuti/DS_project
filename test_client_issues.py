#!/usr/bin/env python3
"""
Test script to identify issues with the client.py reconnection mechanism
"""
import ast
import sys
import os

def analyze_client_code():
    """Analyze the client.py file for syntax and logical issues"""
    
    client_path = "/Users/parisasokuti/my git repo/DS_project/backend/client.py"
    
    print("=== Analyzing client.py for issues ===\n")
    
    # 1. Check for syntax errors
    print("1. Checking syntax...")
    try:
        with open(client_path, 'r') as f:
            code = f.read()
        
        # Parse the code
        ast.parse(code)
        print("   ✅ Syntax is valid")
    except SyntaxError as e:
        print(f"   ❌ Syntax error: {e}")
        print(f"   Line {e.lineno}: {e.text}")
        return False
    except Exception as e:
        print(f"   ❌ Error reading file: {e}")
        return False
    
    # 2. Check for incomplete functions
    print("\n2. Checking for incomplete functions...")
    incomplete_functions = []
    
    # Look for function definitions that have missing return statements or incomplete logic
    lines = code.split('\n')
    for i, line in enumerate(lines, 1):
        # Check for functions that have incomplete conditional blocks
        if 'if choice.lower() == \'exit\':' in line:
            # Look at the next few lines to see if there's a proper return
            next_lines = lines[i:i+3]
            has_return = any('return' in l for l in next_lines)
            if not has_return:
                incomplete_functions.append(f"Line {i}: Missing return statement after exit check")
    
    if incomplete_functions:
        print("   ❌ Found incomplete functions:")
        for func in incomplete_functions:
            print(f"      {func}")
    else:
        print("   ✅ No incomplete functions found")
    
    # 3. Check for duplicate message handlers
    print("\n3. Checking for duplicate message handlers...")
    handlers = {}
    for i, line in enumerate(lines, 1):
        if 'elif msg_type ==' in line:
            msg_type = line.split("'")[1] if "'" in line else line.split('"')[1] if '"' in line else "unknown"
            if msg_type in handlers:
                print(f"   ❌ Duplicate handler for '{msg_type}' at lines {handlers[msg_type]} and {i}")
            else:
                handlers[msg_type] = i
    
    if len(handlers) > 0:
        print(f"   ✅ Found {len(handlers)} unique message handlers")
    
    # 4. Check for missing imports
    print("\n4. Checking for missing imports...")
    missing_imports = []
    
    # Check if queue is imported at the top
    if 'import queue' not in code[:500]:  # Check first 500 characters
        if 'import queue' in code:
            missing_imports.append("'queue' imported inside function instead of at top")
        else:
            missing_imports.append("'queue' module not imported")
    
    # Check for hashlib, socket, getpass
    if 'import hashlib' not in code[:500]:
        missing_imports.append("'hashlib' imported inside function instead of at top")
    
    if missing_imports:
        print("   ❌ Missing/misplaced imports:")
        for imp in missing_imports:
            print(f"      {imp}")
    else:
        print("   ✅ All imports appear to be properly placed")
    
    # 5. Check for logical issues in sort_hand
    print("\n5. Checking sort_hand function logic...")
    sort_hand_issues = []
    
    # Look for the sort_hand function
    sort_hand_start = code.find('def sort_hand(hand, hokm):')
    if sort_hand_start == -1:
        sort_hand_issues.append("sort_hand function not found")
    else:
        # Extract the function
        sort_hand_end = code.find('\n\ndef ', sort_hand_start)
        if sort_hand_end == -1:
            sort_hand_end = code.find('\n\n# ', sort_hand_start)
        
        if sort_hand_end != -1:
            sort_hand_code = code[sort_hand_start:sort_hand_end]
            
            # Check for logical issues
            if 'parse(card)[0].upper() if parse(card)[0].upper() in rank_values else parse(card)[1]' in sort_hand_code:
                sort_hand_issues.append("Incorrect logic in rank_values lookup - using suit instead of rank")
            
            if 'suits_order.index(parse(card)[0])' in sort_hand_code:
                if 'if parse(card)[0] in suits_order' not in sort_hand_code:
                    sort_hand_issues.append("Missing safety check for suits_order.index()")
    
    if sort_hand_issues:
        print("   ❌ Issues in sort_hand function:")
        for issue in sort_hand_issues:
            print(f"      {issue}")
    else:
        print("   ✅ sort_hand function appears correct")
    
    # 6. Check for session file handling issues
    print("\n6. Checking session file handling...")
    session_issues = []
    
    # Check if SESSION_FILE is properly defined
    if 'SESSION_FILE = ' not in code:
        session_issues.append("SESSION_FILE not defined")
    
    # Check for proper error handling in session file operations
    session_operations = code.count('open(SESSION_FILE')
    try_blocks = code.count('try:')
    
    if session_operations > try_blocks:
        session_issues.append("Some session file operations may not have proper error handling")
    
    if session_issues:
        print("   ❌ Session file handling issues:")
        for issue in session_issues:
            print(f"      {issue}")
    else:
        print("   ✅ Session file handling appears correct")
    
    print("\n=== Analysis complete ===")
    return True

if __name__ == "__main__":
    analyze_client_code()
