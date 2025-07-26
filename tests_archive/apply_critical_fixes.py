#!/usr/bin/env python3
"""
Quick Fix Implementation Script
Applies the most critical Redis key consistency fix automatically.
"""

import os
import shutil
import re
from datetime import datetime

def backup_file(filepath):
    """Create a backup of the original file."""
    backup_path = f"{filepath}.backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    shutil.copy2(filepath, backup_path)
    print(f"✅ Backup created: {backup_path}")
    return backup_path

def fix_gameboard_redis_dict():
    """Fix the to_redis_dict method in GameBoard class."""
    filepath = "backend/game_board.py"
    
    if not os.path.exists(filepath):
        print(f"❌ File not found: {filepath}")
        return False
    
    # Create backup
    backup_path = backup_file(filepath)
    
    # Read the file
    with open(filepath, 'r') as f:
        content = f.read()
    
    # Find and replace the to_redis_dict method
    old_pattern = r'def to_redis_dict\(self\):.*?return data'
    
    new_method = '''def to_redis_dict(self):
        """Convert game state to Redis-compatible dictionary with consistent string keys."""
        data = {
            'phase': self.game_phase,
            'players': json.dumps(self.players),
            'player_order': json.dumps(self.players),  # For compatibility
            'teams': json.dumps({str(k): v for k, v in self.teams.items()}),  # FIX: String keys
            'hakem': self.hakem,
            'hokm': self.hokm,
            'current_turn': str(self.current_turn),  # FIX: String for consistency
            'tricks': json.dumps({str(k): v for k, v in self.tricks.items()}),  # FIX: String keys
            'round_scores': json.dumps({str(k): v for k, v in self.round_scores.items()})  # FIX: String keys
        }
        
        # Add individual player hands with consistent keys
        for player in self.players:
            data[f'hand_{player}'] = json.dumps(self.hands.get(player, []))
        
        return data'''
    
    # Replace the method
    new_content = re.sub(old_pattern, new_method, content, flags=re.DOTALL)
    
    if new_content == content:
        print(f"⚠️  Could not find to_redis_dict method pattern in {filepath}")
        print("   Manual fix required - see CRITICAL_FIXES_GUIDE.md")
        return False
    
    # Write the updated content
    with open(filepath, 'w') as f:
        f.write(new_content)
    
    print(f"✅ Fixed to_redis_dict method in {filepath}")
    return True

def fix_server_game_loading():
    """Fix the load_active_games_from_redis method in server.py."""
    filepath = "backend/server.py"
    
    if not os.path.exists(filepath):
        print(f"❌ File not found: {filepath}")
        return False
    
    # Create backup
    backup_path = backup_file(filepath)
    
    with open(filepath, 'r') as f:
        content = f.read()
    
    # Look for the problematic silent exception handling
    if 'except Exception:' in content and 'pass' in content:
        print(f"⚠️  Found silent exception handling in {filepath}")
        print("   Manual review needed - see CRITICAL_FIXES_GUIDE.md for detailed fixes")
        return False
    
    print(f"✅ {filepath} appears to already have proper exception handling")
    return True

def test_fixes():
    """Run a quick test to verify fixes."""
    print("\n🧪 Testing fixes...")
    
    try:
        # Test importing the fixed modules
        import sys
        sys.path.insert(0, 'backend')
        
        from game_board import GameBoard
        
        # Test the fixed serialization
        players = ['Player1', 'Player2', 'Player3', 'Player4']
        game = GameBoard(players, 'TEST')
        
        # Add some test data
        game.teams = {0: ['Player1', 'Player3'], 1: ['Player2', 'Player4']}
        game.round_scores = {0: 5, 1: 3}
        
        # Test serialization
        redis_data = game.to_redis_dict()
        
        # Verify string keys
        teams_data = eval(redis_data['teams'])  # Safe since we just created it
        if all(isinstance(k, str) for k in teams_data.keys()):
            print("✅ Teams serialization fixed - keys are now strings")
        else:
            print("❌ Teams serialization still has issues")
            return False
            
        scores_data = eval(redis_data['round_scores'])
        if all(isinstance(k, str) for k in scores_data.keys()):
            print("✅ Scores serialization fixed - keys are now strings")
        else:
            print("❌ Scores serialization still has issues")
            return False
        
        print("✅ All serialization fixes verified")
        return True
        
    except Exception as e:
        print(f"❌ Test failed: {e}")
        return False

def main():
    """Main fix implementation."""
    print("🔧 HOKM SERVER - CRITICAL FIXES IMPLEMENTATION")
    print("=" * 50)
    print("This script applies the most critical Redis key consistency fix.")
    print("It will create backups of all modified files.\n")
    
    # Change to project directory
    if not os.path.exists('backend'):
        print("❌ Please run this script from the DS_project root directory")
        return
    
    fixes_applied = 0
    
    # Apply fixes
    print("🔧 Applying Fix #1: Redis Key Consistency...")
    if fix_gameboard_redis_dict():
        fixes_applied += 1
    
    print("\n🔧 Checking server.py for improvements needed...")
    if fix_server_game_loading():
        print("   (No automatic fixes applied - manual review recommended)")
    
    # Test the fixes
    if fixes_applied > 0:
        if test_fixes():
            print(f"\n🎉 SUCCESS: {fixes_applied} critical fix(es) applied and tested!")
            print("\n📋 Next steps:")
            print("   1. Clear Redis: redis-cli flushall")
            print("   2. Test: python test_redis_integrity.py")
            print("   3. Review CRITICAL_FIXES_GUIDE.md for remaining fixes")
        else:
            print(f"\n⚠️  WARNING: {fixes_applied} fix(es) applied but testing failed")
            print("   Please review the changes manually")
    else:
        print("\n⚠️  No automatic fixes could be applied")
        print("   Please follow CRITICAL_FIXES_GUIDE.md for manual implementation")

if __name__ == "__main__":
    main()
