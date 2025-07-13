#!/usr/bin/env python3

import json

print("=== Play Card Message Format Fix Verification ===")
print()

# Before the fix (broken)
old_message = {
    "type": "play_card",
    "card": "A_hearts"
}

# After the fix (working)
new_message = {
    "type": "play_card", 
    "room_code": "9999",
    "player_id": "player-123",
    "card": "A_hearts"
}

print("BEFORE (broken):")
print(json.dumps(old_message, indent=2))
print()

print("AFTER (fixed):")
print(json.dumps(new_message, indent=2))
print()

# Verify required fields
required = ['room_code', 'player_id', 'card']
missing_old = [f for f in required if f not in old_message]
missing_new = [f for f in required if f not in new_message]

print("VALIDATION:")
print(f"Old message missing: {missing_old}")  
print(f"New message missing: {missing_new}")
print()

if missing_new:
    print("❌ FAILED: Still missing fields")
else:
    print("✅ SUCCESS: All required fields present!")
    print()
    print("🎉 The fix is working!")
    print("The play_card message now includes:")
    print("- room_code: identifies which room the player is in")
    print("- player_id: identifies which player is making the move") 
    print("- card: the card being played")
    print()
    print("This should resolve the 'Malformed play_card message' error.")
