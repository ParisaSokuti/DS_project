#!/usr/bin/env python3
"""
Test script for Hokm Game Authentication System
"""
import requests
import json
import sys
from datetime import datetime

BASE_URL = "http://localhost:5000/api/auth"

def test_health():
    """Test health endpoint"""
    print("Testing health endpoint...")
    try:
        response = requests.get(f"{BASE_URL}/health")
        if response.status_code == 200:
            print("✓ Health endpoint working")
            return True
        else:
            print(f"✗ Health endpoint failed: {response.status_code}")
            return False
    except Exception as e:
        print(f"✗ Health endpoint error: {e}")
        return False

def test_registration():
    """Test user registration"""
    print("\nTesting user registration...")
    
    user_data = {
        "username": f"testuser_{int(datetime.now().timestamp())}",
        "password": "testpass123",
        "email": "test@example.com",
        "display_name": "Test User"
    }
    
    try:
        response = requests.post(f"{BASE_URL}/register", json=user_data)
        data = response.json()
        
        if response.status_code == 201 and data.get("success"):
            print("✓ User registration successful")
            print(f"  Player ID: {data.get('player_id')}")
            print(f"  Username: {data.get('username')}")
            print(f"  Token: {data.get('token')[:20]}...")
            return data
        else:
            print(f"✗ Registration failed: {data.get('message')}")
            return None
    except Exception as e:
        print(f"✗ Registration error: {e}")
        return None

def test_login(username, password):
    """Test user login"""
    print(f"\nTesting login for user: {username}")
    
    login_data = {
        "username": username,
        "password": password
    }
    
    try:
        response = requests.post(f"{BASE_URL}/login", json=login_data)
        data = response.json()
        
        if response.status_code == 200 and data.get("success"):
            print("✓ User login successful")
            print(f"  Player ID: {data.get('player_id')}")
            print(f"  Username: {data.get('username')}")
            print(f"  Rating: {data.get('rating')}")
            return data
        else:
            print(f"✗ Login failed: {data.get('message')}")
            return None
    except Exception as e:
        print(f"✗ Login error: {e}")
        return None

def test_profile(token):
    """Test profile endpoint"""
    print(f"\nTesting profile endpoint...")
    
    headers = {"Authorization": f"Bearer {token}"}
    
    try:
        response = requests.get(f"{BASE_URL}/profile", headers=headers)
        data = response.json()
        
        if response.status_code == 200 and data.get("success"):
            print("✓ Profile retrieval successful")
            player = data.get("player", {})
            print(f"  Username: {player.get('username')}")
            print(f"  Display Name: {player.get('display_name')}")
            print(f"  Rating: {player.get('rating')}")
            print(f"  Total Games: {player.get('total_games')}")
            return True
        else:
            print(f"✗ Profile retrieval failed: {data.get('message')}")
            return False
    except Exception as e:
        print(f"✗ Profile error: {e}")
        return False

def test_stats(token):
    """Test stats endpoint"""
    print(f"\nTesting stats endpoint...")
    
    headers = {"Authorization": f"Bearer {token}"}
    
    try:
        response = requests.get(f"{BASE_URL}/stats", headers=headers)
        data = response.json()
        
        if response.status_code == 200 and data.get("success"):
            print("✓ Stats retrieval successful")
            stats = data.get("stats", {})
            print(f"  Rating: {stats.get('rating')}")
            print(f"  Total Games: {stats.get('total_games')}")
            print(f"  Wins: {stats.get('wins')}")
            print(f"  Win Percentage: {stats.get('win_percentage')}%")
            return True
        else:
            print(f"✗ Stats retrieval failed: {data.get('message')}")
            return False
    except Exception as e:
        print(f"✗ Stats error: {e}")
        return False

def test_token_verification(token):
    """Test token verification"""
    print(f"\nTesting token verification...")
    
    headers = {"Authorization": f"Bearer {token}"}
    
    try:
        response = requests.get(f"{BASE_URL}/verify", headers=headers)
        data = response.json()
        
        if response.status_code == 200 and data.get("success"):
            print("✓ Token verification successful")
            user = data.get("user", {})
            print(f"  Player ID: {user.get('player_id')}")
            print(f"  Username: {user.get('username')}")
            return True
        else:
            print(f"✗ Token verification failed: {data.get('message')}")
            return False
    except Exception as e:
        print(f"✗ Token verification error: {e}")
        return False

def test_username_check():
    """Test username availability check"""
    print(f"\nTesting username availability check...")
    
    test_data = {"username": "testuser_available"}
    
    try:
        response = requests.post(f"{BASE_URL}/check-username", json=test_data)
        data = response.json()
        
        if response.status_code == 200 and data.get("success"):
            print("✓ Username check successful")
            print(f"  Available: {data.get('available')}")
            return True
        else:
            print(f"✗ Username check failed: {data.get('message')}")
            return False
    except Exception as e:
        print(f"✗ Username check error: {e}")
        return False

def main():
    """Run all tests"""
    print("🎮 Hokm Game Authentication System Test")
    print("=" * 50)
    
    # Test health endpoint
    if not test_health():
        print("\n❌ Server is not running or not accessible")
        print("Make sure to run: python backend/app.py")
        sys.exit(1)
    
    # Test registration
    user_data = test_registration()
    if not user_data:
        print("\n❌ Registration test failed")
        sys.exit(1)
    
    username = user_data.get("username")
    password = "testpass123"
    token = user_data.get("token")
    
    # Test login
    login_data = test_login(username, password)
    if not login_data:
        print("\n❌ Login test failed")
        sys.exit(1)
    
    # Use token from login (should be the same, but let's be safe)
    token = login_data.get("token")
    
    # Test token verification
    if not test_token_verification(token):
        print("\n❌ Token verification test failed")
        sys.exit(1)
    
    # Test profile
    if not test_profile(token):
        print("\n❌ Profile test failed")
        sys.exit(1)
    
    # Test stats
    if not test_stats(token):
        print("\n❌ Stats test failed")
        sys.exit(1)
    
    # Test username availability
    if not test_username_check():
        print("\n❌ Username check test failed")
        sys.exit(1)
    
    print("\n" + "=" * 50)
    print("✅ All authentication tests passed!")
    print("\nThe authentication system is working correctly.")
    print("You can now integrate it with your game logic.")
    print(f"\nTest user created:")
    print(f"  Username: {username}")
    print(f"  Password: {password}")
    print(f"  Player ID: {user_data.get('player_id')}")

if __name__ == "__main__":
    main()
