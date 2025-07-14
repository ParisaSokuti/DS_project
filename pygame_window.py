import pygame
import sys
from game_resources import GameResources

# Initialize Pygame
pygame.init()

# Constants
WINDOW_WIDTH = 1024
WINDOW_HEIGHT = 768
FPS = 60

# Colors
WHITE = (255, 255, 255)
BLACK = (0, 0, 0)
BLUE = (0, 0, 255)
GREEN = (0, 128, 0)

def main():
    # Load all game resources
    print("Loading game resources...")
    resources = GameResources()
    resources.load_all_resources()
    
    # Create the display window
    screen = pygame.display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT))
    pygame.display.set_caption("Pygame Window - Hokm Game")
    
    # Create a clock object to control frame rate
    clock = pygame.time.Clock()
    
    # Get resources for display
    background = resources.get_ui_image("background")
    title_font = resources.get_font("title")
    medium_font = resources.get_font("medium")
    
    # Sample cards to display
    sample_cards = [
        "A_of_hearts",
        "K_of_spades", 
        "Q_of_diamonds",
        "J_of_clubs",
        "10_of_hearts"
    ]
    
    # Main game loop
    running = True
    while running:
        # Handle events
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    running = False
                elif event.key == pygame.K_SPACE:
                    # Play a sound effect if available
                    resources.play_sound("card_flip", 0.5)
        
        # Draw background
        if background:
            screen.blit(background, (0, 0))
        else:
            screen.fill(GREEN)
        
        # Draw title
        if title_font:
            title_text = title_font.render("Hokm Game", True, WHITE)
            title_rect = title_text.get_rect(center=(WINDOW_WIDTH // 2, 80))
            screen.blit(title_text, title_rect)
        
        # Draw sample cards
        card_y = 200
        card_spacing = 80
        start_x = (WINDOW_WIDTH - (len(sample_cards) * card_spacing)) // 2
        
        for i, card_name in enumerate(sample_cards):
            card_image = resources.get_card(card_name)
            if card_image:
                card_x = start_x + (i * card_spacing)
                screen.blit(card_image, (card_x, card_y))
        
        # Draw instructions
        if medium_font:
            instructions = [
                "Sample card images loaded from resources",
                "Press SPACE to play card flip sound",
                "Press ESC to exit"
            ]
            
            for i, instruction in enumerate(instructions):
                text = medium_font.render(instruction, True, WHITE)
                text_rect = text.get_rect(center=(WINDOW_WIDTH // 2, 350 + i * 30))
                screen.blit(text, text_rect)
        
        # Draw resource statistics
        if medium_font:
            stats = [
                f"Cards loaded: {len(resources.cards)}",
                f"Fonts loaded: {len(resources.fonts)}",
                f"UI images loaded: {len(resources.ui_images)}",
                f"Sounds loaded: {len(resources.sounds)}"
            ]
            
            for i, stat in enumerate(stats):
                text = medium_font.render(stat, True, WHITE)
                screen.blit(text, (20, 20 + i * 25))
        
        # Update the display
        pygame.display.flip()
        
        # Control frame rate
        clock.tick(FPS)
    
    # Quit Pygame
    pygame.quit()
    sys.exit()

if __name__ == "__main__":
    main()
