#!/usr/bin/env python3
"""
Simple card image generator for testing the resource system.
This creates placeholder card images for all 52 cards.
"""

import pygame
import os
import sys

def create_sample_card_images():
    """Create sample card images for testing."""
    
    # Initialize Pygame
    pygame.init()
    
    # Card dimensions
    card_width = 71
    card_height = 96
    
    # Create assets directory structure
    assets_dir = "assets"
    cards_dir = os.path.join(assets_dir, "cards")
    
    if not os.path.exists(cards_dir):
        os.makedirs(cards_dir)
        print(f"Created directory: {cards_dir}")
    
    # Card data
    suits = ['hearts', 'diamonds', 'clubs', 'spades']
    ranks = ['2', '3', '4', '5', '6', '7', '8', '9', '10', 'J', 'Q', 'K', 'A']
    
    # Suit colors
    suit_colors = {
        'hearts': (255, 0, 0),    # Red
        'diamonds': (255, 0, 0),  # Red
        'clubs': (0, 0, 0),       # Black
        'spades': (0, 0, 0)       # Black
    }
    
    # Suit symbols
    suit_symbols = {
        'hearts': '♥',
        'diamonds': '♦',
        'clubs': '♣',
        'spades': '♠'
    }
    
    print("Creating sample card images...")
    
    cards_created = 0
    
    for suit in suits:
        for rank in ranks:
            # Create card surface
            card_surface = pygame.Surface((card_width, card_height))
            card_surface.fill((255, 255, 255))  # White background
            
            # Draw border
            pygame.draw.rect(card_surface, (0, 0, 0), card_surface.get_rect(), 2)
            
            # Get colors
            text_color = suit_colors[suit]
            
            # Draw rank in corners
            font_large = pygame.font.Font(None, 24)
            rank_text = font_large.render(rank, True, text_color)
            
            # Top-left corner
            card_surface.blit(rank_text, (5, 5))
            
            # Bottom-right corner (rotated)
            rotated_rank = pygame.transform.rotate(rank_text, 180)
            card_surface.blit(rotated_rank, (card_width - 25, card_height - 25))
            
            # Draw suit symbol in center
            font_symbol = pygame.font.Font(None, 36)
            symbol_text = font_symbol.render(suit_symbols[suit], True, text_color)
            symbol_rect = symbol_text.get_rect(center=(card_width // 2, card_height // 2))
            card_surface.blit(symbol_text, symbol_rect)
            
            # Draw suit name
            font_small = pygame.font.Font(None, 16)
            suit_text = font_small.render(suit.upper(), True, text_color)
            suit_rect = suit_text.get_rect(center=(card_width // 2, card_height // 2 + 20))
            card_surface.blit(suit_text, suit_rect)
            
            # Save the card
            card_name = f"{rank}_of_{suit}"
            card_file = os.path.join(cards_dir, f"{card_name}.png")
            pygame.image.save(card_surface, card_file)
            cards_created += 1
            
            print(f"Created: {card_name}.png")
    
    # Create card back
    card_back = pygame.Surface((card_width, card_height))
    card_back.fill((0, 0, 139))  # Dark blue background
    
    # Draw border
    pygame.draw.rect(card_back, (255, 255, 255), card_back.get_rect(), 2)
    
    # Draw pattern
    for i in range(0, card_width, 10):
        for j in range(0, card_height, 10):
            if (i + j) % 20 == 0:
                pygame.draw.circle(card_back, (255, 255, 255), (i, j), 2)
    
    # Draw "HOKM" text
    font = pygame.font.Font(None, 24)
    text = font.render("HOKM", True, (255, 255, 255))
    text_rect = text.get_rect(center=(card_width // 2, card_height // 2))
    card_back.blit(text, text_rect)
    
    # Save card back
    card_back_file = os.path.join(cards_dir, "card_back.png")
    pygame.image.save(card_back, card_back_file)
    print("Created: card_back.png")
    
    print(f"\nCreated {cards_created} card images + 1 card back")
    print(f"Total files: {cards_created + 1}")

def create_sample_ui_images():
    """Create sample UI images."""
    
    ui_dir = os.path.join("assets", "ui")
    if not os.path.exists(ui_dir):
        os.makedirs(ui_dir)
        print(f"Created directory: {ui_dir}")
    
    # UI elements to create
    ui_elements = {
        'background': (1024, 768, (0, 128, 0)),
        'table': (800, 600, (0, 100, 0)),
        'button_normal': (120, 40, (200, 200, 200)),
        'button_hover': (120, 40, (220, 220, 220)),
        'button_pressed': (120, 40, (180, 180, 180)),
        'player_area': (200, 150, (139, 69, 19)),
        'score_panel': (200, 100, (255, 255, 255)),
        'trump_indicator': (60, 60, (255, 215, 0)),
        'trick_area': (300, 200, (0, 80, 0)),
    }
    
    print("\nCreating sample UI images...")
    
    for name, (width, height, color) in ui_elements.items():
        surface = pygame.Surface((width, height))
        surface.fill(color)
        
        # Add border
        pygame.draw.rect(surface, (0, 0, 0), surface.get_rect(), 2)
        
        # Add text label
        font = pygame.font.Font(None, 24)
        text = font.render(name.upper().replace('_', ' '), True, (0, 0, 0))
        text_rect = text.get_rect(center=(width // 2, height // 2))
        surface.blit(text, text_rect)
        
        # Save the image
        ui_file = os.path.join(ui_dir, f"{name}.png")
        pygame.image.save(surface, ui_file)
        print(f"Created: {name}.png")

def main():
    """Main function to create all sample assets."""
    
    print("=" * 50)
    print("HOKM GAME SAMPLE ASSET CREATOR")
    print("=" * 50)
    
    try:
        # Create sample card images
        create_sample_card_images()
        
        # Create sample UI images
        create_sample_ui_images()
        
        print("\n" + "=" * 50)
        print("Sample assets created successfully!")
        print("You can now run the resource loading test.")
        print("=" * 50)
        
    except Exception as e:
        print(f"Error creating sample assets: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
