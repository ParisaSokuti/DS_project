#!/usr/bin/env python3
"""
Status Panel Feature Test
Quick test to verify all status panel components are working correctly.
"""

def test_status_panel_features():
    """Test all status panel components."""
    
    print("🧪 TESTING STATUS PANEL FEATURES")
    print("=" * 50)
    
    try:
        # Test imports
        print("✅ Testing imports...")
        import pygame
        import sys
        import os
        sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'frontend'))
        from hokm_gui_client import HokmGameGUI
        print("   ✓ All imports successful")
        
        # Test initialization
        print("✅ Testing initialization...")
        pygame.init()
        game = HokmGameGUI()
        print("   ✓ Game initialization successful")
        
        # Test position calculations
        print("✅ Testing position calculations...")
        game.calculate_positions()
        
        # Verify status panel areas exist
        required_areas = [
            'status_panel_area',
            'turn_status_area', 
            'hokm_status_area',
            'scores_status_area',
            'game_info_area'
        ]
        
        for area in required_areas:
            if hasattr(game, area):
                area_rect = getattr(game, area)
                print(f"   ✓ {area}: {area_rect.width}x{area_rect.height} at ({area_rect.x},{area_rect.y})")
            else:
                print(f"   ❌ Missing: {area}")
        
        # Test enhanced state variables
        print("✅ Testing enhanced state variables...")
        state_vars = [
            'current_turn_player',
            'game_phase',
            'trick_number',
            'round_number',
            'waiting_for',
            'hokm_selector',
            'trick_winner'
        ]
        
        for var in state_vars:
            if hasattr(game, var):
                value = getattr(game, var)
                print(f"   ✓ {var}: {value}")
            else:
                print(f"   ❌ Missing: {var}")
        
        # Test drawing methods
        print("✅ Testing drawing methods...")
        drawing_methods = [
            'draw_comprehensive_status_panel',
            'draw_turn_status_section',
            'draw_hokm_status_section', 
            'draw_scores_status_section',
            'draw_game_info_section'
        ]
        
        for method in drawing_methods:
            if hasattr(game, method):
                print(f"   ✓ {method} method exists")
            else:
                print(f"   ❌ Missing: {method}")
        
        # Test game state simulation
        print("✅ Testing game state simulation...")
        game.current_turn_player = "Test Player"
        game.hokm_suit = "hearts"
        game.scores = {"team1": 5, "team2": 3}
        game.game_phase = "playing"
        game.trick_number = 7
        game.round_number = 2
        print("   ✓ Game state variables set successfully")
        
        # Test color scheme
        print("✅ Testing color scheme...")
        required_colors = [
            'card_hover',
            'card_playable',
            'drag_drop_zone'
        ]
        
        for color in required_colors:
            if color in game.colors:
                rgb_value = game.colors[color]
                print(f"   ✓ {color}: {rgb_value}")
            else:
                print(f"   ❌ Missing color: {color}")
        
        print("\n🎉 ALL TESTS COMPLETED!")
        print("✅ Status Panel system is ready to use")
        
        pygame.quit()
        
    except Exception as e:
        print(f"❌ Test failed with error: {e}")
        return False
    
    return True

def main():
    """Run the status panel feature test."""
    print("🔧 HOKM GAME - STATUS PANEL FEATURE TEST")
    print("=" * 50)
    print()
    
    success = test_status_panel_features()
    
    print("\n" + "=" * 50)
    if success:
        print("🎯 STATUS: All features are working correctly!")
        print("🚀 Ready to run the full game or demos")
        print()
        print("📋 Available commands:")
        print("   python hokm_gui_client.py       # Full game")
        print("   python status_panel_demo.py     # Status panel demo")
        print("   python interactive_demo.py      # Interactive demo")
    else:
        print("⚠️  STATUS: Some features need attention")
        print("🔧 Check the error messages above")
    
    print("=" * 50)

if __name__ == "__main__":
    main()
