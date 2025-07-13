#!/usr/bin/env python3
"""
🎮 Hokm Game Client
Run this to join the game as a player
"""

import sys
import os

# Add the project root to Python path
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_root)

# Import and run the client
if __name__ == "__main__":
    print("🎮 Connecting to Hokm Game...")
    print("=" * 40)
    
    try:
        from backend.client import main
        import asyncio
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n🛑 Client shutting down...")
    except Exception as e:
        print(f"❌ Fatal error: {str(e)}")
        sys.exit(1)
