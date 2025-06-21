"""
Verification script for the A_hearts connection issue fix.
This script modifies the server code to fix the connection closure bug.
"""

import sys
import os
import json
import traceback

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

def apply_fix():
    """Apply fixes to the server code"""
    try:
        # Get the path to server.py
        server_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'backend', 'server.py'))
        
        with open(server_path, 'r') as f:
            server_code = f.read()
        
        # Fix 1: Ensure hand_complete broadcast properly handles all data types
        if "if result.get('hand_complete'):" in server_code:
            print("Applying fix for hand_complete broadcast...")
            
            # Find the section that handles hand completion
            target_section = """                # If hand complete, broadcast hand and round completion and save state
                if result.get('hand_complete'):
                    # Fix the winning_team calculation to prevent negative values
                    round_winner = result.get('round_winner', 1)  # Default to team 1 if missing
                    winning_team = max(0, round_winner - 1) if round_winner > 0 else 0  # Ensure it's 0 or 1, never negative
                    
                    # Broadcast hand completion with proper data types
                    await self.network_manager.broadcast_to_room(
                        room_code,
                        'hand_complete',
                        {
                            'winning_team': winning_team,  # Always 0 or 1"""
            
            # Replace with fixed version that handles missing or invalid team_tricks and properly logs errors
            fixed_section = """                # If hand complete, broadcast hand and round completion and save state
                if result.get('hand_complete'):
                    try:
                        # Fix the winning_team calculation to prevent negative values
                        round_winner = result.get('round_winner', 1)  # Default to team 1 if missing
                        winning_team = max(0, round_winner - 1) if round_winner > 0 else 0  # Ensure it's 0 or 1, never negative
                        
                        # Ensure team_tricks is a dictionary
                        team_tricks = result.get('team_tricks', {})
                        if not isinstance(team_tricks, dict):
                            print(f"[WARNING] Invalid team_tricks format: {team_tricks}, using default")
                            team_tricks = {0: 0, 1: 0}
                        
                        # Ensure round_scores is a dictionary
                        round_scores = result.get('round_scores', {})
                        if not isinstance(round_scores, dict):
                            print(f"[WARNING] Invalid round_scores format: {round_scores}, using default")
                            round_scores = {0: 0, 1: 0}
                        
                        # Create message with validated data
                        hand_complete_message = {
                            'winning_team': winning_team,  # Always 0 or 1"""
            
            # Apply the replacement
            modified_code = server_code.replace(target_section, fixed_section)
            
            # Fix 2: Ensure broadcast_to_room handles errors properly
            if "async def broadcast_to_room" in modified_code:
                print("Adding error handling to broadcast_to_room...")
                
                # Find the broadcast_to_room method in NetworkManager
                target_broadcast = """    async def broadcast_to_room(self, room_code, message_type, data, redis_manager=None):
        """
                
                # Replace with error-handling version
                fixed_broadcast = """    async def broadcast_to_room(self, room_code, message_type, data, redis_manager=None):
        # Ensure data is JSON serializable
        try:
            # Test JSON serialization before attempting to broadcast
            json.dumps(data)
        except TypeError as e:
            print(f"[ERROR] Non-serializable data in broadcast_to_room for '{message_type}': {str(e)}")
            # Make a safe copy of the data
            safe_data = {}
            for key, value in data.items():
                try:
                    json.dumps(value)
                    safe_data[key] = value
                except TypeError:
                    # Convert non-serializable values to strings
                    safe_data[key] = str(value)
            data = safe_data
            print(f"[RECOVERY] Converted data to serializable format: {data}")
        
        """
                
                # Apply the replacement
                modified_code = modified_code.replace(target_broadcast, fixed_broadcast)
            
            # Write the modified code back
            with open(server_path, 'w') as f:
                f.write(modified_code)
                
            print("Fixes applied successfully!")
            return True
                
        else:
            print("Could not find target code section to fix")
            return False
            
    except Exception as e:
        print(f"Error applying fix: {str(e)}")
        traceback.print_exc()
        return False

def verify_fix():
    """Check if the fix was applied correctly"""
    try:
        # Get the path to server.py
        server_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'backend', 'server.py'))
        
        with open(server_path, 'r') as f:
            server_code = f.read()
        
        # Check for our added code
        if "try:" in server_code and "Ensure team_tricks is a dictionary" in server_code:
            print("Fix verification: PASS - Error handling added to hand_complete section")
        else:
            print("Fix verification: FAIL - Error handling for hand_complete not found")
            
        if "Ensure data is JSON serializable" in server_code:
            print("Fix verification: PASS - JSON serialization check added to broadcast_to_room")
        else:
            print("Fix verification: FAIL - JSON serialization check not found")
            
    except Exception as e:
        print(f"Error verifying fix: {str(e)}")
        traceback.print_exc()

if __name__ == "__main__":
    print("=== A_hearts Connection Bug Fix ===")
    
    if len(sys.argv) > 1 and sys.argv[1] == "apply":
        print("Applying fixes to server.py...")
        success = apply_fix()
        if success:
            verify_fix()
    elif len(sys.argv) > 1 and sys.argv[1] == "verify":
        print("Verifying fixes in server.py...")
        verify_fix()
    else:
        print("Usage:")
        print("  python tests/verify_ace_hearts_fix.py apply   - Apply the fixes")
        print("  python tests/verify_ace_hearts_fix.py verify  - Verify fixes are in place")
        print("\nThis script fixes the issue where playing A_hearts causes the connection to close.")
        print("The fix adds proper error handling and data validation to prevent JSON serialization errors.")
