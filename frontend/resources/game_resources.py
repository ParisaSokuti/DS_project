import pygame
import os
import sys
from typing import Dict, Optional

class GameResources:
    """
    Resource manager for the Hokm game.
    Handles loading and caching of all game assets including cards, fonts, and UI elements.
    """
    
    def __init__(self):
        self.cards: Dict[str, pygame.Surface] = {}
        self.fonts: Dict[str, pygame.font.Font] = {}
        self.ui_images: Dict[str, pygame.Surface] = {}
        self.sounds: Dict[str, pygame.mixer.Sound] = {}
        
        # Card suits and ranks
        self.suits = ['hearts', 'diamonds', 'clubs', 'spades']
        self.ranks = ['2', '3', '4', '5', '6', '7', '8', '9', '10', 'J', 'Q', 'K', 'A']
        
        # Paths
        self.assets_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'assets')
        self.cards_dir = os.path.join(self.assets_dir, 'cards')
        self.fonts_dir = os.path.join(self.assets_dir, 'fonts')
        self.ui_dir = os.path.join(self.assets_dir, 'ui')
        self.sounds_dir = os.path.join(self.assets_dir, 'sounds')
        
        # Card dimensions
        self.card_width = 71
        self.card_height = 96
        
        # Initialize pygame mixer for sounds
        pygame.mixer.init()
        
    def create_directories(self):
        """Create asset directories if they don't exist."""
        directories = [self.assets_dir, self.cards_dir, self.fonts_dir, self.ui_dir, self.sounds_dir]
        for directory in directories:
            if not os.path.exists(directory):
                os.makedirs(directory)
                print(f"Created directory: {directory}")
    
    def create_placeholder_card(self, card_name: str) -> pygame.Surface:
        """Create a placeholder card image if the actual image doesn't exist."""
        surface = pygame.Surface((self.card_width, self.card_height))
        surface.fill((255, 255, 255))  # White background
        
        # Draw border
        pygame.draw.rect(surface, (0, 0, 0), surface.get_rect(), 2)
        
        # Add card name text
        font = pygame.font.Font(None, 24)
        text_lines = card_name.split('_')
        
        y_offset = 10
        for line in text_lines:
            text = font.render(line, True, (0, 0, 0))
            text_rect = text.get_rect(centerx=self.card_width // 2, y=y_offset)
            surface.blit(text, text_rect)
            y_offset += 25
        
        return surface
    
    def load_card_images(self):
        """Load all 52 standard playing card images."""
        print("Loading card images...")
        
        # Create cards directory if it doesn't exist
        if not os.path.exists(self.cards_dir):
            os.makedirs(self.cards_dir)
        
        cards_loaded = 0
        
        for suit in self.suits:
            for rank in self.ranks:
                # Standard card naming convention
                card_name = f"{rank}_of_{suit}"
                
                # Try multiple file formats
                card_file = None
                for ext in ['.png', '.jpg', '.jpeg', '.gif']:
                    potential_file = os.path.join(self.cards_dir, f"{card_name}{ext}")
                    if os.path.exists(potential_file):
                        card_file = potential_file
                        break
                
                if card_file:
                    try:
                        card_surface = pygame.image.load(card_file)
                        card_surface = pygame.transform.scale(card_surface, (self.card_width, self.card_height))
                        self.cards[card_name] = card_surface
                        cards_loaded += 1
                    except pygame.error as e:
                        print(f"Error loading card {card_name}: {e}")
                        self.cards[card_name] = self.create_placeholder_card(card_name)
                else:
                    # Create placeholder if image doesn't exist
                    self.cards[card_name] = self.create_placeholder_card(card_name)
        
        # Load card back
        card_back_file = None
        for ext in ['.png', '.jpg', '.jpeg', '.gif']:
            potential_file = os.path.join(self.cards_dir, f"card_back{ext}")
            if os.path.exists(potential_file):
                card_back_file = potential_file
                break
        
        if card_back_file:
            try:
                card_back = pygame.image.load(card_back_file)
                card_back = pygame.transform.scale(card_back, (self.card_width, self.card_height))
                self.cards['card_back'] = card_back
            except pygame.error as e:
                print(f"Error loading card back: {e}")
                self.cards['card_back'] = self.create_placeholder_card("BACK")
        else:
            self.cards['card_back'] = self.create_placeholder_card("BACK")
        
        print(f"Loaded {cards_loaded} card images (52 total cards)")
        return len(self.cards)
    
    def load_fonts(self):
        """Load fonts for text display."""
        print("Loading fonts...")
        
        # Create fonts directory if it doesn't exist
        if not os.path.exists(self.fonts_dir):
            os.makedirs(self.fonts_dir)
        
        # Define font sizes and names
        font_configs = {
            'small': 16,
            'medium': 24,
            'large': 32,
            'xlarge': 48,
            'title': 64
        }
        
        # Try to load custom fonts first
        custom_font_file = None
        for ext in ['.ttf', '.otf']:
            potential_file = os.path.join(self.fonts_dir, f"game_font{ext}")
            if os.path.exists(potential_file):
                custom_font_file = potential_file
                break
        
        for name, size in font_configs.items():
            try:
                if custom_font_file:
                    self.fonts[name] = pygame.font.Font(custom_font_file, size)
                else:
                    # Use default system font
                    self.fonts[name] = pygame.font.Font(None, size)
                print(f"Loaded font: {name} (size {size})")
            except pygame.error as e:
                print(f"Error loading font {name}: {e}")
                self.fonts[name] = pygame.font.Font(None, size)
        
        return len(self.fonts)
    
    def create_placeholder_ui_image(self, name: str, width: int, height: int, color: tuple) -> pygame.Surface:
        """Create a placeholder UI image."""
        surface = pygame.Surface((width, height))
        surface.fill(color)
        
        # Add border
        pygame.draw.rect(surface, (0, 0, 0), surface.get_rect(), 2)
        
        # Add text
        font = pygame.font.Font(None, 24)
        text = font.render(name.upper(), True, (0, 0, 0))
        text_rect = text.get_rect(center=(width // 2, height // 2))
        surface.blit(text, text_rect)
        
        return surface
    
    def load_ui_images(self):
        """Load UI images like buttons and backgrounds."""
        print("Loading UI images...")
        
        # Create UI directory if it doesn't exist
        if not os.path.exists(self.ui_dir):
            os.makedirs(self.ui_dir)
        
        # Define UI elements to load
        ui_elements = {
            'button_normal': (120, 40, (200, 200, 200)),
            'button_hover': (120, 40, (220, 220, 220)),
            'button_pressed': (120, 40, (180, 180, 180)),
            'background': (1024, 768, (0, 128, 0)),  # Green background
            'table': (800, 600, (0, 100, 0)),  # Darker green table
            'player_area': (200, 150, (139, 69, 19)),  # Brown player area
            'score_panel': (200, 100, (255, 255, 255)),  # White score panel
            'trump_indicator': (60, 60, (255, 215, 0)),  # Gold trump indicator
            'trick_area': (300, 200, (0, 80, 0)),  # Dark green trick area
        }
        
        ui_loaded = 0
        
        for name, (width, height, color) in ui_elements.items():
            # Try to load from file first
            ui_file = None
            for ext in ['.png', '.jpg', '.jpeg', '.gif']:
                potential_file = os.path.join(self.ui_dir, f"{name}{ext}")
                if os.path.exists(potential_file):
                    ui_file = potential_file
                    break
            
            if ui_file:
                try:
                    ui_surface = pygame.image.load(ui_file)
                    ui_surface = pygame.transform.scale(ui_surface, (width, height))
                    self.ui_images[name] = ui_surface
                    ui_loaded += 1
                except pygame.error as e:
                    print(f"Error loading UI image {name}: {e}")
                    self.ui_images[name] = self.create_placeholder_ui_image(name, width, height, color)
            else:
                # Create placeholder
                self.ui_images[name] = self.create_placeholder_ui_image(name, width, height, color)
        
        print(f"Loaded {ui_loaded} UI images ({len(ui_elements)} total)")
        return len(self.ui_images)
    
    def load_sounds(self):
        """Load sound effects."""
        print("Loading sounds...")
        
        # Create sounds directory if it doesn't exist
        if not os.path.exists(self.sounds_dir):
            os.makedirs(self.sounds_dir)
        
        # Define sound effects
        sound_files = [
            'card_flip',
            'card_place',
            'button_click',
            'game_start',
            'round_win',
            'game_win',
            'hokm_selected',
            'trick_won'
        ]
        
        sounds_loaded = 0
        
        for sound_name in sound_files:
            sound_file = None
            for ext in ['.wav', '.ogg', '.mp3']:
                potential_file = os.path.join(self.sounds_dir, f"{sound_name}{ext}")
                if os.path.exists(potential_file):
                    sound_file = potential_file
                    break
            
            if sound_file:
                try:
                    sound = pygame.mixer.Sound(sound_file)
                    self.sounds[sound_name] = sound
                    sounds_loaded += 1
                except pygame.error as e:
                    print(f"Error loading sound {sound_name}: {e}")
            else:
                print(f"Sound file not found: {sound_name}")
        
        print(f"Loaded {sounds_loaded} sound effects")
        return len(self.sounds)
    
    def load_all_resources(self):
        """Load all game resources."""
        print("=" * 50)
        print("Loading Game Resources...")
        print("=" * 50)
        
        self.create_directories()
        
        cards_count = self.load_card_images()
        fonts_count = self.load_fonts()
        ui_count = self.load_ui_images()
        sounds_count = self.load_sounds()
        
        print("=" * 50)
        print("Resource Loading Complete!")
        print(f"Cards: {cards_count}")
        print(f"Fonts: {fonts_count}")
        print(f"UI Images: {ui_count}")
        print(f"Sounds: {sounds_count}")
        print("=" * 50)
        
        return {
            'cards': cards_count,
            'fonts': fonts_count,
            'ui_images': ui_count,
            'sounds': sounds_count
        }
    
    def get_card(self, card_name: str) -> Optional[pygame.Surface]:
        """Get a card image by name."""
        return self.cards.get(card_name)
    
    def get_font(self, font_name: str) -> Optional[pygame.font.Font]:
        """Get a font by name."""
        return self.fonts.get(font_name)
    
    def get_ui_image(self, image_name: str) -> Optional[pygame.Surface]:
        """Get a UI image by name."""
        return self.ui_images.get(image_name)
    
    def get_sound(self, sound_name: str) -> Optional[pygame.mixer.Sound]:
        """Get a sound by name."""
        return self.sounds.get(sound_name)
    
    def play_sound(self, sound_name: str, volume: float = 1.0):
        """Play a sound effect."""
        sound = self.get_sound(sound_name)
        if sound:
            sound.set_volume(volume)
            sound.play()
    
    def convert_card_name_to_key(self, card_str: str) -> str:
        """
        Convert card string from game format to resource key.
        E.g., "Ace of Hearts" -> "A_of_hearts"
        """
        if not card_str:
            return ""
        
        # Handle different card formats
        parts = card_str.lower().split()
        if len(parts) >= 3:  # "Ace of Hearts"
            rank = parts[0]
            suit = parts[2]
            
            # Convert rank names to symbols
            rank_map = {
                'ace': 'A',
                'jack': 'J',
                'queen': 'Q',
                'king': 'K'
            }
            
            rank = rank_map.get(rank, rank)
            return f"{rank}_of_{suit}"
        
        return card_str.lower()
    
    def list_available_cards(self):
        """List all available card images."""
        print("\nAvailable Card Images:")
        for i, card_name in enumerate(sorted(self.cards.keys()), 1):
            print(f"{i:2d}. {card_name}")
    
    def get_card_dimensions(self) -> tuple:
        """Get the standard card dimensions."""
        return (self.card_width, self.card_height)


# Convenience function to create and load resources
def load_game_resources() -> GameResources:
    """Create and load all game resources."""
    resources = GameResources()
    resources.load_all_resources()
    return resources


# Example usage and testing
if __name__ == "__main__":
    # Initialize Pygame
    pygame.init()
    
    # Create resource manager
    resources = load_game_resources()
    
    # Test resource access
    print("\n" + "=" * 50)
    print("Testing Resource Access:")
    print("=" * 50)
    
    # Test card access
    test_card = resources.get_card("A_of_hearts")
    print(f"Ace of Hearts loaded: {test_card is not None}")
    
    # Test font access
    title_font = resources.get_font("title")
    print(f"Title font loaded: {title_font is not None}")
    
    # Test UI image access
    background = resources.get_ui_image("background")
    print(f"Background image loaded: {background is not None}")
    
    # List some available cards
    resources.list_available_cards()
    
    print("\nResource manager ready for use!")
