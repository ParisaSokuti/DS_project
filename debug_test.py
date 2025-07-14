#!/usr/bin/env python3
print("Starting message processing test...")

try:
    import queue
    print("Queue import: OK")
    
    import time
    print("Time import: OK")
    
    # Simple test
    q = queue.Queue()
    q.put("test_message")
    msg = q.get()
    print(f"Queue test: {msg}")
    
    print("✅ Basic functionality working!")
    
except Exception as e:
    print(f"❌ Error: {e}")
    import traceback
    traceback.print_exc()
