#!/usr/bin/env python3
"""
🎴 Hokm Game Server
Run this to start the game server on ws://localhost:8765
"""

import sys
import os

# Add the project root to Python path
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_root)

# Import and run the server
if __name__ == "__main__":
    print("🎴 Starting Hokm Game Server...")
    print("=" * 50)
    
    try:
        from backend.server import main
        import asyncio
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n🛑 Server shutting down...")
    except Exception as e:
        print(f"❌ Fatal error: {str(e)}")
        sys.exit(1)
