#!/usr/bin/env python3
"""
Secondary server startup script for network access
This should be run on the friend's machine (192.168.1.92)
"""
import asyncio
import subprocess
import sys
import os

def main():
    """Start the secondary server accessible from network"""
    
    print("🚀 Starting Secondary Hokm Game Server")
    print("=" * 50)
    print("📡 Server will be accessible from network")
    print("🔧 Port: 8765")
    print("🌐 Listening on all interfaces")
    print("⚠️  Make sure Windows Firewall allows Python on port 8765")
    print("=" * 50)
    
    try:
        # Change to the correct directory
        script_dir = os.path.dirname(os.path.abspath(__file__))
        os.chdir(script_dir)
        
        # Start the server using the existing server.py with network binding
        print("🎯 Starting server using backend/server.py...")
        
        # Run the server with arguments for secondary server
        cmd = [
            sys.executable, 
            "backend/server.py", 
            "--port", "8765", 
            "--instance-name", "secondary",
            "--host", "0.0.0.0"  # Listen on all interfaces
        ]
        
        print(f"� Running command: {' '.join(cmd)}")
        
        # Start the server process
        process = subprocess.run(cmd, check=True)
        
    except KeyboardInterrupt:
        print("\n🛑 Shutting down secondary server...")
    except subprocess.CalledProcessError as e:
        print(f"❌ Server failed to start: {e}")
        print("💡 Make sure you're in the hokm_game directory")
        print("💡 Make sure backend/server.py exists")
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
    finally:
        print("✅ Secondary server setup complete")

if __name__ == "__main__":
    main()
