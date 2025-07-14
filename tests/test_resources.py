#!/usr/bin/env python3
"""
Test script for the game resources system.
This script demonstrates loading and accessing all game resources.
"""

import pygame
import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'frontend'))
from resources.game_resources import GameResources

def test_resource_loading():
    """Test the resource loading system."""
    
    # Initialize Pygame
    pygame.init()
    
    print("=" * 60)
    print("HOKM GAME RESOURCE LOADING TEST")
    print("=" * 60)
    
    # Create resource manager
    resources = GameResources()
    
    # Load all resources
    stats = resources.load_all_resources()
    
    # Test individual resource access
    print("\n" + "=" * 40)
    print("TESTING RESOURCE ACCESS")
    print("=" * 40)
    
    # Test card access
    test_cards = ["A_of_hearts", "K_of_spades", "Q_of_diamonds", "J_of_clubs"]
    print("\nTesting card access:")
    for card in test_cards:
        card_img = resources.get_card(card)
        status = "✓" if card_img else "✗"
        print(f"  {status} {card}")
    
    # Test card back
    card_back = resources.get_card("card_back")
    status = "✓" if card_back else "✗"
    print(f"  {status} card_back")
    
    # Test font access
    print("\nTesting font access:")
    font_sizes = ["small", "medium", "large", "xlarge", "title"]
    for font_name in font_sizes:
        font = resources.get_font(font_name)
        status = "✓" if font else "✗"
        print(f"  {status} {font_name} font")
    
    # Test UI image access
    print("\nTesting UI image access:")
    ui_elements = ["background", "button_normal", "table", "player_area"]
    for ui_name in ui_elements:
        ui_img = resources.get_ui_image(ui_name)
        status = "✓" if ui_img else "✗"
        print(f"  {status} {ui_name}")
    
    # Test sound access
    print("\nTesting sound access:")
    sound_names = ["card_flip", "card_place", "button_click", "game_start"]
    for sound_name in sound_names:
        sound = resources.get_sound(sound_name)
        status = "✓" if sound else "✗"
        print(f"  {status} {sound_name}")
    
    # Display directory structure
    print("\n" + "=" * 40)
    print("DIRECTORY STRUCTURE")
    print("=" * 40)
    
    assets_dir = resources.assets_dir
    if os.path.exists(assets_dir):
        print(f"\nAssets directory: {assets_dir}")
        for root, dirs, files in os.walk(assets_dir):
            level = root.replace(assets_dir, '').count(os.sep)
            indent = ' ' * 2 * level
            print(f"{indent}{os.path.basename(root)}/")
            subindent = ' ' * 2 * (level + 1)
            for file in files:
                print(f"{subindent}{file}")
    else:
        print(f"\nAssets directory not found: {assets_dir}")
    
    # Card conversion test
    print("\n" + "=" * 40)
    print("CARD NAME CONVERSION TEST")
    print("=" * 40)
    
    test_conversions = [
        "Ace of Hearts",
        "King of Spades", 
        "Queen of Diamonds",
        "Jack of Clubs",
        "10 of Hearts"
    ]
    
    for card_str in test_conversions:
        converted = resources.convert_card_name_to_key(card_str)
        print(f"'{card_str}' -> '{converted}'")
    
    # Summary
    print("\n" + "=" * 60)
    print("RESOURCE LOADING SUMMARY")
    print("=" * 60)
    print(f"Total cards loaded: {len(resources.cards)}")
    print(f"Total fonts loaded: {len(resources.fonts)}")
    print(f"Total UI images loaded: {len(resources.ui_images)}")
    print(f"Total sounds loaded: {len(resources.sounds)}")
    print("\nResource loading test complete!")
    print("To add actual images, place them in the assets/ subdirectories.")
    print("=" * 60)
    
    return resources

def create_sample_assets():
    """Create some sample asset files for testing."""
    print("\nCreating sample asset structure...")
    
    # This would create actual sample files in a real implementation
    # For now, we'll just show the expected structure
    expected_structure = {
        "assets/cards/": [
            "A_of_hearts.png", "K_of_spades.png", "Q_of_diamonds.png", 
            "J_of_clubs.png", "card_back.png", "... (52 total cards)"
        ],
        "assets/fonts/": [
            "game_font.ttf"
        ],
        "assets/ui/": [
            "background.png", "button_normal.png", "button_hover.png",
            "table.png", "player_area.png"
        ],
        "assets/sounds/": [
            "card_flip.wav", "card_place.wav", "button_click.wav",
            "game_start.wav", "round_win.wav"
        ]
    }
    
    print("\nExpected asset structure:")
    for directory, files in expected_structure.items():
        print(f"\n{directory}")
        for file in files:
            print(f"  {file}")

if __name__ == "__main__":
    # Run the test
    try:
        resources = test_resource_loading()
        
        # Show sample asset structure
        create_sample_assets()
        
        # Option to run visual test
        print("\n" + "=" * 60)
        response = input("Run visual test window? (y/n): ").strip().lower()
        if response == 'y':
            print("Running visual test...")
            # Import and run the pygame window
            from pygame_window import PygameWindow
            pygame_window = PygameWindow()
            pygame_window.main()
            
    except KeyboardInterrupt:
        print("\nTest interrupted by user.")
    except Exception as e:
        print(f"\nError during testing: {e}")
        sys.exit(1)
