#!/usr/bin/env python3
"""
Network connectivity test for distributed server setup
"""
import socket
import subprocess
import platform

def test_ping(ip_address):
    """Test if the IP address is reachable"""
    try:
        param = '-n' if platform.system().lower() == 'windows' else '-c'
        command = ['ping', param, '1', ip_address]
        result = subprocess.run(command, capture_output=True, text=True, timeout=10)
        return result.returncode == 0
    except Exception as e:
        print(f"❌ Ping test failed: {e}")
        return False

def test_port(ip_address, port, timeout=5):
    """Test if a specific port is open on the IP address"""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        result = sock.connect_ex((ip_address, port))
        sock.close()
        return result == 0
    except Exception as e:
        print(f"❌ Port test failed: {e}")
        return False

def main():
    print("🔍 Testing Network Connectivity for Distributed Setup")
    print("=" * 60)
    
    friend_ip = "192.168.1.92"
    server_port = 8765
    
    print(f"🎯 Target: {friend_ip}:{server_port}")
    print()
    
    # Test 1: Ping
    print("1. Testing basic connectivity (ping)...")
    if test_ping(friend_ip):
        print(f"✅ Ping to {friend_ip} successful")
    else:
        print(f"❌ Ping to {friend_ip} failed")
        print("💡 Check if both machines are on the same WiFi network")
        return
    
    # Test 2: Port connectivity
    print(f"\n2. Testing port {server_port} connectivity...")
    if test_port(friend_ip, server_port):
        print(f"✅ Port {server_port} is open on {friend_ip}")
        print("🎮 Secondary server is running and accessible!")
    else:
        print(f"❌ Port {server_port} is not accessible on {friend_ip}")
        print("💡 Possible issues:")
        print("   - Secondary server is not running")
        print("   - Windows Firewall is blocking the port")
        print("   - Server is not listening on 0.0.0.0 (all interfaces)")
        print("\n🔧 To fix:")
        print("   1. On friend's machine, run: python start_secondary_server.py")
        print("   2. Allow Python through Windows Firewall")
        print("   3. Verify server starts with 'Listening on all interfaces'")
    
    print("\n" + "=" * 60)
    print("🚀 Setup Instructions:")
    print("Your machine (Primary):")
    print("  1. python backend/server.py --port 8765 --instance-name primary")
    print("  2. python backend/load_balancer.py")
    print()
    print("Friend's machine (Secondary):")
    print("  1. python start_secondary_server.py")
    print("  2. Allow Python through Windows Firewall")
    print()
    print("Clients:")
    print("  python backend/client.py (connects to load balancer)")

if __name__ == "__main__":
    main()
