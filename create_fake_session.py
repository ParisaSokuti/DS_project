import json

# Create a fake session file with a properly formatted but invalid player ID
session_file = ".player_session_test123"
fake_player_id = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"

with open(session_file, 'w') as f:
    f.write(fake_player_id)

print(f"Created session file {session_file} with fake player ID: {fake_player_id}")
print("Now run: PLAYER_SESSION='.player_session_test123' python -m backend.client")
print("This should trigger the 'Player not found in room' error and test input handling")
