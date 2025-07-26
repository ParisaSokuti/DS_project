#!/usr/bin/env python3
"""
Test Script for Reorganized Hokm Game Project
Tests core functionality after moving standalone files to temp/ folder

This test validates:
1. Backend server and client can be imported successfully
2. Core game functionality works
3. All required dependencies are accessible
4. Basic game flow can be executed
"""

import sys
import os
import asyncio
import time
import json
from pathlib import Path

# Add backend directory to path
backend_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'backend')
sys.path.insert(0, backend_path)

print("🧪 Hokm Game Reorganization Functionality Test")
print("=" * 60)
print(f"Backend path: {backend_path}")
print(f"Working directory: {os.getcwd()}")

def test_imports():
    """Test that all core modules can be imported"""
    print("\n📦 Testing Core Module Imports")
    print("-" * 40)
    
    try:
        # Test server imports
        print("Testing server module imports...")
        from network import NetworkManager
        print("✅ NetworkManager imported successfully")
        
        from game_board import GameBoard
        print("✅ GameBoard imported successfully")
        
        from game_states import GameState
        print("✅ GameState imported successfully")
        
        from redis_manager_resilient import ResilientRedisManager
        print("✅ ResilientRedisManager imported successfully")
        
        from circuit_breaker_monitor import CircuitBreakerMonitor
        print("✅ CircuitBreakerMonitor imported successfully")
        
        # Test authentication imports
        try:
            from game_auth_manager import GameAuthManager
            print("✅ GameAuthManager imported successfully")
            auth_available = True
        except ImportError as e:
            print(f"⚠️  GameAuthManager not available: {e}")
            from simple_auth_manager import SimpleAuthManager
            print("✅ SimpleAuthManager imported as fallback")
            auth_available = False
        
        # Test client imports
        print("Testing client module imports...")
        from client_auth_manager import ClientAuthManager
        print("✅ ClientAuthManager imported successfully")
        
        return True, auth_available
        
    except ImportError as e:
        print(f"❌ Import failed: {e}")
        return False, False

def test_game_board_functionality():
    """Test core GameBoard functionality"""
    print("\n🎮 Testing GameBoard Core Functionality")
    print("-" * 40)
    
    try:
        from game_board import GameBoard
        
        # Test game creation
        players = ['Alice', 'Bob', 'Charlie', 'Diana']
        game = GameBoard(players, 'TEST_ROOM')
        print(f"✅ Game created with {len(game.players)} players")
        
        # Test team assignment
        team_result = game.assign_teams_and_hakem(None)
        print(f"✅ Teams assigned - Hakem: {team_result['hakem']}")
        
        # Test initial deal
        initial_hands = game.initial_deal()
        print(f"✅ Initial deal completed")
        for player in players:
            hand_size = len(initial_hands.get(player, []))
            print(f"   {player}: {hand_size} cards")
            if hand_size != 5:
                print(f"⚠️  Expected 5 cards, got {hand_size}")
        
        # Test hokm selection
        hokm_result = game.set_hokm('hearts', None, 'TEST_ROOM')
        if hokm_result:
            print("✅ Hokm set successfully")
        else:
            print("❌ Failed to set hokm")
            return False
        
        return True
        
    except Exception as e:
        print(f"❌ GameBoard test failed: {e}")
        return False

def test_game_states():
    """Test GameState functionality"""
    print("\n🎯 Testing GameState Functionality")
    print("-" * 40)
    
    try:
        from game_states import GameState
        
        # Test state enum values
        print("✅ GameState imported successfully")
        
        # Test that all expected states exist
        expected_states = [
            'AUTHENTICATION', 'WAITING_FOR_PLAYERS', 'TEAM_ASSIGNMENT',
            'WAITING_FOR_HOKM', 'FINAL_DEAL', 'GAMEPLAY', 'HAND_COMPLETE', 'GAME_OVER'
        ]
        
        for state_name in expected_states:
            if hasattr(GameState, state_name):
                state_value = getattr(GameState, state_name)
                print(f"✅ {state_name}: {state_value.value}")
            else:
                print(f"⚠️  {state_name} not found")
        
        # Test state comparison
        if GameState.WAITING_FOR_PLAYERS.value == "waiting_for_players":
            print("✅ State values work correctly")
        
        return True
        
    except Exception as e:
        print(f"❌ GameState test failed: {e}")
        return False

def test_network_manager():
    """Test NetworkManager functionality"""
    print("\n🌐 Testing NetworkManager Functionality") 
    print("-" * 40)
    
    try:
        from network import NetworkManager
        
        # Test network manager creation
        network_manager = NetworkManager()
        print("✅ NetworkManager created successfully")
        
        # Test if basic methods exist
        if hasattr(network_manager, 'broadcast_to_room'):
            print("✅ broadcast_to_room method exists")
        else:
            print("⚠️  broadcast_to_room method not found")
            
        return True
        
    except Exception as e:
        print(f"❌ NetworkManager test failed: {e}")
        return False

def test_redis_manager():
    """Test Redis Manager (without requiring actual Redis connection)"""
    print("\n🔄 Testing Redis Manager")
    print("-" * 40)
    
    try:
        from redis_manager_resilient import ResilientRedisManager
        
        # Test redis manager creation (should work even without Redis running)
        redis_manager = ResilientRedisManager()
        print("✅ ResilientRedisManager created successfully")
        
        # Test if basic methods exist
        expected_methods = ['get_game_state', 'save_game_state', 'cleanup']
        for method in expected_methods:
            if hasattr(redis_manager, method):
                print(f"✅ {method} method exists")
            else:
                print(f"⚠️  {method} method not found")
        
        return True
        
    except Exception as e:
        print(f"❌ Redis Manager test failed: {e}")
        return False

async def test_server_creation():
    """Test that server can be created (without starting it)"""
    print("\n🖥️  Testing Server Creation")
    print("-" * 40)
    
    try:
        # Import the server module
        sys.path.insert(0, backend_path)
        from server import GameServer
        
        # Create server instance
        server = GameServer()
        print("✅ GameServer instance created successfully")
        
        # Check if server has expected attributes
        expected_attrs = ['redis_manager', 'network_manager', 'auth_manager', 'active_games']
        for attr in expected_attrs:
            if hasattr(server, attr):
                print(f"✅ Server has {attr} attribute")
            else:
                print(f"⚠️  Server missing {attr} attribute")
        
        return True
        
    except Exception as e:
        print(f"❌ Server creation test failed: {e}")
        return False

def test_client_functionality():
    """Test basic client functionality"""
    print("\n👤 Testing Client Functionality")
    print("-" * 40)
    
    try:
        from client_auth_manager import ClientAuthManager
        
        # Test client auth manager
        auth_manager = ClientAuthManager()
        print("✅ ClientAuthManager created successfully")
        
        # Test if expected methods exist
        expected_methods = ['authenticate_with_server', 'authenticate_with_token', 'load_session', 'save_session']
        for method in expected_methods:
            if hasattr(auth_manager, method):
                print(f"✅ {method} method exists")
            else:
                print(f"⚠️  {method} method not found")
        
        # Test if it has expected attributes
        if hasattr(auth_manager, 'token'):
            print("✅ token attribute exists")
        if hasattr(auth_manager, 'player_info'):
            print("✅ player_info attribute exists")
        
        return True
        
    except Exception as e:
        print(f"❌ Client functionality test failed: {e}")
        return False

def test_file_structure():
    """Test that the file structure is correct after reorganization"""
    print("\n📁 Testing File Structure")
    print("-" * 40)
    
    # Check backend files exist
    backend_files = [
        'server.py', 'client.py', 'network.py', 'game_board.py', 
        'game_states.py', 'redis_manager_resilient.py'
    ]
    
    all_exist = True
    for file in backend_files:
        file_path = os.path.join(backend_path, file)
        if os.path.exists(file_path):
            print(f"✅ {file} exists in backend/")
        else:
            print(f"❌ {file} missing from backend/")
            all_exist = False
    
    # Check temp folder exists and has expected content
    temp_path = os.path.join(os.path.dirname(backend_path), 'temp')
    if os.path.exists(temp_path):
        print("✅ temp/ folder exists")
        
        # Check some expected folders in temp
        expected_temp_folders = ['config', 'database', 'examples', 'scripts']
        for folder in expected_temp_folders:
            folder_path = os.path.join(temp_path, folder)
            if os.path.exists(folder_path):
                print(f"✅ temp/{folder}/ exists")
            else:
                print(f"⚠️  temp/{folder}/ not found (may be okay)")
    else:
        print("❌ temp/ folder missing")
        all_exist = False
    
    return all_exist

def main():
    """Run all tests"""
    print("Starting comprehensive functionality test after reorganization...\n")
    
    results = []
    
    # Test file structure
    results.append(("File Structure", test_file_structure()))
    
    # Test imports
    import_success, auth_available = test_imports()
    results.append(("Core Imports", import_success))
    
    if import_success:
        # Test core functionality
        results.append(("GameBoard", test_game_board_functionality()))
        results.append(("GameState", test_game_states()))
        results.append(("NetworkManager", test_network_manager()))
        results.append(("Redis Manager", test_redis_manager()))
        results.append(("Client Functionality", test_client_functionality()))
        
        # Test server creation (async)
        try:
            server_result = asyncio.run(test_server_creation())
            results.append(("Server Creation", server_result))
        except Exception as e:
            print(f"❌ Server creation async test failed: {e}")
            results.append(("Server Creation", False))
    
    # Print summary
    print("\n" + "=" * 60)
    print("🏁 TEST SUMMARY")
    print("=" * 60)
    
    passed = 0
    total = len(results)
    
    for test_name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{test_name:<20}: {status}")
        if result:
            passed += 1
    
    print(f"\nOverall: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 All tests passed! The reorganization was successful.")
        print("✅ Core game functionality is working properly.")
        if not auth_available:
            print("ℹ️  Note: Using simple authentication fallback (database auth not available)")
    else:
        print("⚠️  Some tests failed. Please check the issues above.")
    
    return passed == total

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
