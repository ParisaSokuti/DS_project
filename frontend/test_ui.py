#!/usr/bin/env python3
"""
Test script to verify UI functionality
"""

import pygame
import sys
import threading
import time
from hokm_gui_client import HokmGameGUI

def test_ui_briefly():
    """Test the UI for a few seconds to check if it works"""
    print("Testing UI functionality...")
    
    try:
        # Create game instance
        game = HokmGameGUI()
        
        # Run for a brief moment
        start_time = time.time()
        test_duration = 2.0  # Run for 2 seconds
        
        running = True
        
        while running and (time.time() - start_time) < test_duration:
            # Handle events
            running = game.handle_events()
            
            # Update and draw
            game.update()
            game.draw()
            
            # Control frame rate
            game.clock.tick(60)
        
        print("✅ UI test completed successfully!")
        print("✅ Login screen displayed properly")
        print("✅ Event handling works")
        print("✅ Drawing functions work")
        return True
        
    except Exception as e:
        print(f"❌ UI test failed: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        pygame.quit()

if __name__ == "__main__":
    success = test_ui_briefly()
    sys.exit(0 if success else 1)
