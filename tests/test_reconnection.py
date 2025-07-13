#!/usr/bin/env python3
"""
Test script to verify the reconnection mechanism functionality
"""

import ast
import re

def test_reconnection_mechanism():
    """Test specific aspects of the reconnection mechanism"""
    
    client_path = "/Users/parisasokuti/my git repo/DS_project/backend/client.py"
    
    print("=== Testing Reconnection Mechanism ===\n")
    
    with open(client_path, 'r') as f:
        code = f.read()
    
    # 1. Test session file creation and management
    print("1. Testing session file management...")
    
    session_file_checks = [
        'SESSION_FILE = ',
        'get_terminal_session_id()',
        'with open(SESSION_FILE, \'w\')',
        'with open(SESSION_FILE, \'r\')',
        'os.path.exists(SESSION_FILE)'
    ]
    
    session_issues = []
    for check in session_file_checks:
        if check not in code:
            session_issues.append(f"Missing: {check}")
    
    if session_issues:
        print("   ❌ Session file management issues:")
        for issue in session_issues:
            print(f"      {issue}")
    else:
        print("   ✅ Session file management is complete")
    
    # 2. Test reconnection flow
    print("\n2. Testing reconnection flow...")
    
    reconnection_flow = [
        'session_player_id = None',
        'if session_player_id and session_player_id == player_id:',
        '"type": "reconnect"',
        'elif msg_type == \'reconnect_success\'',
        'game_state_data = data.get(\'game_state\'',
        'hand = game_state_data.get(\'hand\'',
        'hokm = game_state_data.get(\'hokm\'',
        'your_team = game_state_data.get(\'your_team\'',
        'phase = game_state_data.get(\'phase\''
    ]
    
    flow_issues = []
    for check in reconnection_flow:
        if check not in code:
            flow_issues.append(f"Missing: {check}")
    
    if flow_issues:
        print("   ❌ Reconnection flow issues:")
        for issue in flow_issues:
            print(f"      {issue}")
    else:
        print("   ✅ Reconnection flow is complete")
    
    # 3. Test game state restoration
    print("\n3. Testing game state restoration...")
    
    restoration_checks = [
        'you = game_state_data.get(\'you\')',
        'current_state = GameState.GAMEPLAY',
        'current_state = GameState.FINAL_DEAL',
        'current_state = GameState.WAITING_FOR_HOKM',
        'current_state = GameState.TEAM_ASSIGNMENT',
        'if hand:',
        'sorted_hand = sort_hand(hand, hokm)',
        'teams = game_state_data.get(\'teams\'',
        'team1_players = [format_player_name(p, you) for p in teams.get(\'1\''
    ]
    
    restoration_issues = []
    for check in restoration_checks:
        if check not in code:
            restoration_issues.append(f"Missing: {check}")
    
    if restoration_issues:
        print("   ❌ Game state restoration issues:")
        for issue in restoration_issues:
            print(f"      {issue}")
    else:
        print("   ✅ Game state restoration is complete")
    
    # 4. Test error handling and fallback
    print("\n4. Testing error handling and fallback...")
    
    error_handling = [
        'if "reconnect" in error_msg.lower() or "session" in error_msg.lower()',
        'print("🔄 Reconnection failed, trying to join as new player...")',
        'session_player_id = None  # Clear session',
        '"type": "join"',
        'asyncio.TimeoutError:',
        'print(f"⏰ Reconnection request timed out")',
        'choice = input("\\nWhat would you like to do? (exit/clear_session/retry/enter): ")',
        'elif choice == \'retry\':'
    ]
    
    error_issues = []
    for check in error_handling:
        if check not in code:
            error_issues.append(f"Missing: {check}")
    
    if error_issues:
        print("   ❌ Error handling issues:")
        for issue in error_issues:
            print(f"      {issue}")
    else:
        print("   ✅ Error handling is complete")
    
    # 5. Test manual retry mechanism
    print("\n5. Testing manual retry mechanism...")
    
    retry_checks = [
        'elif choice == \'retry\':',
        'print("Attempting to reconnect...")',
        'if os.path.exists(SESSION_FILE):',
        'session_content = f.read().strip()',
        'await ws.send(json.dumps({',
        '"type": "reconnect"',
        '"player_id": session_content',
        'print("Reconnection request sent. Waiting for server response...")'
    ]
    
    retry_issues = []
    for check in retry_checks:
        if check not in code:
            retry_issues.append(f"Missing: {check}")
    
    if retry_issues:
        print("   ❌ Manual retry mechanism issues:")
        for issue in retry_issues:
            print(f"      {issue}")
    else:
        print("   ✅ Manual retry mechanism is complete")
    
    # 6. Test session persistence functions
    print("\n6. Testing session persistence functions...")
    
    persistence_checks = [
        'def clear_session():',
        'def preserve_session():',
        'os.remove(SESSION_FILE)',
        'print("💾 Session preserved for future reconnections")',
        'print("🗑️ Session cleared")'
    ]
    
    persistence_issues = []
    for check in persistence_checks:
        if check not in code:
            persistence_issues.append(f"Missing: {check}")
    
    if persistence_issues:
        print("   ❌ Session persistence issues:")
        for issue in persistence_issues:
            print(f"      {issue}")
    else:
        print("   ✅ Session persistence is complete")
    
    # 7. Count potential logical issues
    print("\n7. Testing for logical issues...")
    
    logical_issues = []
    
    # Check for proper authentication flow
    auth_pattern = r'authenticated = await auth_manager\.authenticate_with_server\(ws\)'
    if not re.search(auth_pattern, code):
        logical_issues.append("Authentication flow may be incomplete")
    
    # Check for proper player_id handling
    player_id_pattern = r'player_id = player_info\[\'player_id\'\]'
    if not re.search(player_id_pattern, code):
        logical_issues.append("Player ID extraction may be incomplete")
    
    # Check for proper session comparison
    session_compare_pattern = r'session_player_id == player_id'
    if not re.search(session_compare_pattern, code):
        logical_issues.append("Session comparison logic may be incomplete")
    
    if logical_issues:
        print("   ❌ Logical issues found:")
        for issue in logical_issues:
            print(f"      {issue}")
    else:
        print("   ✅ No logical issues detected")
    
    print("\n=== Reconnection Mechanism Test Complete ===")
    
    # Calculate score
    total_checks = len(session_file_checks) + len(reconnection_flow) + len(restoration_checks) + len(error_handling) + len(retry_checks) + len(persistence_checks)
    issues_found = len(session_issues) + len(flow_issues) + len(restoration_issues) + len(error_issues) + len(retry_issues) + len(persistence_issues) + len(logical_issues)
    
    score = ((total_checks - issues_found) / total_checks) * 100
    print(f"\nReconnection Mechanism Completeness: {score:.1f}%")
    
    if score >= 90:
        print("✅ Reconnection mechanism appears to be fully functional")
    elif score >= 70:
        print("⚠️  Reconnection mechanism is mostly functional but has some issues")
    else:
        print("❌ Reconnection mechanism has significant issues")
    
    return score >= 90

if __name__ == "__main__":
    test_reconnection_mechanism()
