#!/usr/bin/env python3
"""
Analyze the problematic game state for room 9999
"""
import redis
import json
import time

def analyze_game_state():
    """Analyze the game state that's causing issues"""
    print("=== Analyzing Game State for Room 9999 ===")
    
    r = redis.Redis(host='localhost', port=6379, db=0, socket_timeout=10.0)
    
    try:
        key = "game:9999:state"
        print(f"1. Checking if key exists: {key}")
        exists = r.exists(key)
        print(f"   Key exists: {exists}")
        
        if not exists:
            print("   Key doesn't exist, nothing to analyze")
            return
        
        print("2. Getting key type and size...")
        key_type = r.type(key)
        print(f"   Key type: {key_type}")
        
        # Get field count
        field_count = r.hlen(key)
        print(f"   Field count: {field_count}")
        
        print("3. Getting all fields...")
        start_time = time.time()
        raw_state = r.hgetall(key)
        elapsed = time.time() - start_time
        print(f"   Retrieved in {elapsed:.3f}s")
        
        print("4. Analyzing fields...")
        total_size = 0
        for field, value in raw_state.items():
            field_name = field.decode() if isinstance(field, bytes) else field
            value_str = value.decode() if isinstance(value, bytes) else value
            field_size = len(value_str)
            total_size += field_size
            
            print(f"   {field_name}: {field_size} bytes")
            
            # Show first 100 characters of large fields
            if field_size > 100:
                print(f"     Preview: {value_str[:100]}...")
            else:
                print(f"     Value: {value_str}")
            
            # Check if it's valid JSON
            if field_name in ['teams', 'players', 'tricks', 'player_order'] or field_name.startswith('hand_'):
                try:
                    json.loads(value_str)
                    print(f"     ✅ Valid JSON")
                except json.JSONDecodeError as e:
                    print(f"     ❌ Invalid JSON: {e}")
        
        print(f"5. Total data size: {total_size} bytes ({total_size/1024:.2f} KB)")
        
        # Check for suspicious patterns
        print("6. Checking for issues...")
        issues = []
        
        if total_size > 100000:  # 100KB
            issues.append(f"Large data size: {total_size/1024:.2f} KB")
        
        if field_count > 50:
            issues.append(f"Many fields: {field_count}")
        
        # Look for hand data issues
        hand_fields = [f for f in raw_state.keys() if f.decode().startswith('hand_')]
        if len(hand_fields) > 10:
            issues.append(f"Too many hand fields: {len(hand_fields)}")
        
        if issues:
            print("   Issues found:")
            for issue in issues:
                print(f"     - {issue}")
        else:
            print("   No obvious issues detected")
            
        # Recommend cleanup
        print("7. Recommendations:")
        if total_size > 50000:
            print("   - Consider clearing this room data (it's very large)")
        if field_count > 20:
            print("   - Room might have accumulated too much data")
        
        print("   - To clear this room: redis-cli DEL game:9999:state")
        
    except Exception as e:
        print(f"❌ Error analyzing game state: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    analyze_game_state()
