#!/usr/bin/env python3
"""
Enhanced Hokm Game Table Layout Demo
Shows detailed table layout with all player positions and game areas.
"""

import pygame
import sys
from game_resources import GameResources

class HokmTableDemo:
    """Demo class to show the complete table layout."""
    
    def __init__(self):
        pygame.init()
        
        # Screen settings
        self.screen_width = 1200
        self.screen_height = 800
        self.screen = pygame.display.set_mode((self.screen_width, self.screen_height))
        pygame.display.set_caption("Hokm Game - Table Layout Demo")
        
        # Resources
        self.resources = GameResources()
        self.resources.load_all_resources()
        
        # Clock
        self.clock = pygame.time.Clock()
        
        # Colors
        self.colors = {
            'background': (20, 80, 20),
            'table': (0, 120, 0),
            'felt': (0, 100, 0),
            'wood': (139, 69, 19),
            'highlight': (255, 255, 0),
            'text': (255, 255, 255),
            'text_dark': (0, 0, 0),
            'card_outline': (200, 200, 200),
            'played_area': (0, 80, 0),
            'trick_pile': (100, 50, 0)
        }
        
        self.calculate_layout()
        
    def calculate_layout(self):
        """Calculate all layout positions."""
        # Main table (oval in center)
        table_width = 700
        table_height = 500
        self.table_center = (self.screen_width // 2, self.screen_height // 2)
        self.table_rect = pygame.Rect(
            self.table_center[0] - table_width // 2,
            self.table_center[1] - table_height // 2,
            table_width, table_height
        )
        
        # Card dimensions
        card_width, card_height = self.resources.get_card_dimensions()
        
        # Player seating areas
        margin = 50
        hand_width = 450
        hand_height = 80
        
        self.player_areas = {
            'north': {
                'rect': pygame.Rect(
                    self.table_center[0] - hand_width // 2,
                    margin,
                    hand_width, hand_height
                ),
                'name_pos': (self.table_center[0], margin + hand_height + 20),
                'card_count_pos': (self.table_center[0], margin + hand_height + 40)
            },
            'south': {
                'rect': pygame.Rect(
                    self.table_center[0] - hand_width // 2,
                    self.screen_height - margin - hand_height,
                    hand_width, hand_height
                ),
                'name_pos': (self.table_center[0], self.screen_height - margin - hand_height - 20),
                'card_count_pos': (self.table_center[0], self.screen_height - margin - hand_height - 40)
            },
            'east': {
                'rect': pygame.Rect(
                    self.screen_width - margin - hand_height,
                    self.table_center[1] - hand_width // 2,
                    hand_height, hand_width
                ),
                'name_pos': (self.screen_width - margin - hand_height - 20, self.table_center[1]),
                'card_count_pos': (self.screen_width - margin - hand_height - 40, self.table_center[1])
            },
            'west': {
                'rect': pygame.Rect(
                    margin,
                    self.table_center[1] - hand_width // 2,
                    hand_height, hand_width
                ),
                'name_pos': (margin + hand_height + 20, self.table_center[1]),
                'card_count_pos': (margin + hand_height + 40, self.table_center[1])
            }
        }
        
        # Central play area
        play_size = 240
        self.play_area = pygame.Rect(
            self.table_center[0] - play_size // 2,
            self.table_center[1] - play_size // 2,
            play_size, play_size
        )
        
        # Played card positions (4 positions around center)
        self.played_positions = {
            'north': (self.table_center[0] - card_width // 2, self.play_area.y + 20),
            'east': (self.play_area.right - card_width - 20, self.table_center[1] - card_height // 2),
            'south': (self.table_center[0] - card_width // 2, self.play_area.bottom - card_height - 20),
            'west': (self.play_area.x + 20, self.table_center[1] - card_height // 2)
        }
        
        # Trick pile
        self.trick_pile = pygame.Rect(
            self.table_rect.right + 30,
            self.table_center[1] - 60,
            80, 120
        )
        
        # UI areas
        self.info_panel = pygame.Rect(20, 20, 200, 150)
        self.score_panel = pygame.Rect(self.screen_width - 220, 20, 200, 150)
        self.hokm_indicator = pygame.Rect(self.table_center[0] - 30, 20, 60, 60)
        
    def draw_table_surface(self):
        """Draw the main table surface."""
        # Background
        self.screen.fill(self.colors['background'])
        
        # Table felt (oval)
        pygame.draw.ellipse(self.screen, self.colors['table'], self.table_rect)
        pygame.draw.ellipse(self.screen, self.colors['wood'], self.table_rect, 8)
        
        # Inner felt area
        inner_rect = self.table_rect.inflate(-40, -40)
        pygame.draw.ellipse(self.screen, self.colors['felt'], inner_rect)
        
        # Table edge highlights
        pygame.draw.ellipse(self.screen, (180, 100, 50), self.table_rect, 3)
        
    def draw_player_areas(self):
        """Draw areas for each player."""
        font = self.resources.get_font("medium")
        small_font = self.resources.get_font("small")
        
        player_info = {
            'north': {'name': 'North Player', 'cards': 13, 'color': (100, 100, 150)},
            'east': {'name': 'East Player', 'cards': 13, 'color': (150, 100, 100)},
            'south': {'name': 'You', 'cards': 13, 'color': (100, 150, 100)},
            'west': {'name': 'West Player', 'cards': 13, 'color': (150, 150, 100)}
        }
        
        for position, area_info in self.player_areas.items():
            area_rect = area_info['rect']
            info = player_info[position]
            
            # Draw player area
            pygame.draw.rect(self.screen, info['color'], area_rect)
            pygame.draw.rect(self.screen, self.colors['text_dark'], area_rect, 2)
            
            # Draw player name
            if font:
                name_text = font.render(info['name'], True, self.colors['text'])
                name_rect = name_text.get_rect(center=area_info['name_pos'])
                self.screen.blit(name_text, name_rect)
            
            # Draw card count
            if small_font:
                card_text = small_font.render(f"Cards: {info['cards']}", True, self.colors['text'])
                card_rect = card_text.get_rect(center=area_info['card_count_pos'])
                self.screen.blit(card_text, card_rect)
            
            # Draw card placeholders
            self.draw_card_placeholders(position, area_rect, info['cards'])
    
    def draw_card_placeholders(self, position, area_rect, num_cards):
        """Draw placeholder cards for each player."""
        card_width, card_height = self.resources.get_card_dimensions()
        
        if position in ['north', 'south']:
            # Horizontal layout
            max_cards_visible = min(num_cards, 15)
            spacing = (area_rect.width - 20) // max_cards_visible
            start_x = area_rect.x + 10
            
            for i in range(max_cards_visible):
                card_x = start_x + i * spacing
                card_y = area_rect.y + 10
                
                # Draw card outline
                card_rect = pygame.Rect(card_x, card_y, min(spacing - 2, card_width), card_height - 20)
                pygame.draw.rect(self.screen, (60, 60, 60), card_rect)
                pygame.draw.rect(self.screen, self.colors['card_outline'], card_rect, 1)
                
        else:  # east, west
            # Vertical layout
            max_cards_visible = min(num_cards, 15)
            spacing = (area_rect.height - 20) // max_cards_visible
            start_y = area_rect.y + 10
            
            for i in range(max_cards_visible):
                card_x = area_rect.x + 10
                card_y = start_y + i * spacing
                
                # Draw card outline
                card_rect = pygame.Rect(card_x, card_y, card_width - 20, min(spacing - 2, card_height))
                pygame.draw.rect(self.screen, (60, 60, 60), card_rect)
                pygame.draw.rect(self.screen, self.colors['card_outline'], card_rect, 1)
    
    def draw_play_area(self):
        """Draw the central play area."""
        # Play area background
        pygame.draw.rect(self.screen, self.colors['played_area'], self.play_area)
        pygame.draw.rect(self.screen, self.colors['text_dark'], self.play_area, 3)
        
        # Label
        font = self.resources.get_font("medium")
        if font:
            label = font.render("Played Cards", True, self.colors['text'])
            label_rect = label.get_rect(center=(self.play_area.centerx, self.play_area.y - 20))
            self.screen.blit(label, label_rect)
        
        # Draw card position outlines
        card_width, card_height = self.resources.get_card_dimensions()
        small_font = self.resources.get_font("small")
        
        for position, (x, y) in self.played_positions.items():
            card_rect = pygame.Rect(x, y, card_width, card_height)
            
            # Dashed outline
            pygame.draw.rect(self.screen, self.colors['card_outline'], card_rect, 2)
            
            # Position label
            if small_font:
                label = small_font.render(position.upper(), True, self.colors['card_outline'])
                label_rect = label.get_rect(center=card_rect.center)
                self.screen.blit(label, label_rect)
    
    def draw_trick_pile(self):
        """Draw the trick pile area."""
        # Trick pile background
        pygame.draw.rect(self.screen, self.colors['trick_pile'], self.trick_pile)
        pygame.draw.rect(self.screen, self.colors['text_dark'], self.trick_pile, 2)
        
        # Label
        font = self.resources.get_font("medium")
        if font:
            label = font.render("Tricks", True, self.colors['text'])
            label_rect = label.get_rect(center=(self.trick_pile.centerx, self.trick_pile.y - 20))
            self.screen.blit(label, label_rect)
        
        # Trick count
        small_font = self.resources.get_font("small")
        if small_font:
            count = small_font.render("0", True, self.colors['text'])
            count_rect = count.get_rect(center=self.trick_pile.center)
            self.screen.blit(count, count_rect)
    
    def draw_ui_panels(self):
        """Draw UI information panels."""
        # Info panel
        pygame.draw.rect(self.screen, (40, 40, 40), self.info_panel)
        pygame.draw.rect(self.screen, self.colors['text_dark'], self.info_panel, 2)
        
        # Score panel
        pygame.draw.rect(self.screen, (40, 40, 40), self.score_panel)
        pygame.draw.rect(self.screen, self.colors['text_dark'], self.score_panel, 2)
        
        # Hokm indicator
        pygame.draw.rect(self.screen, (200, 200, 0), self.hokm_indicator)
        pygame.draw.rect(self.screen, self.colors['text_dark'], self.hokm_indicator, 2)
        
        font = self.resources.get_font("medium")
        small_font = self.resources.get_font("small")
        
        # Info panel content
        if font and small_font:
            # Info panel
            info_title = font.render("Game Info", True, self.colors['text'])
            self.screen.blit(info_title, (self.info_panel.x + 10, self.info_panel.y + 10))
            
            info_items = [
                "Round: 1",
                "Turn: North",
                "Phase: Playing",
                "Tricks: 0/13"
            ]
            
            for i, item in enumerate(info_items):
                text = small_font.render(item, True, self.colors['text'])
                self.screen.blit(text, (self.info_panel.x + 10, self.info_panel.y + 40 + i * 20))
            
            # Score panel
            score_title = font.render("Scores", True, self.colors['text'])
            self.screen.blit(score_title, (self.score_panel.x + 10, self.score_panel.y + 10))
            
            score_items = [
                "Team 1: 0",
                "Team 2: 0",
                "Hands won:",
                "  Team 1: 0",
                "  Team 2: 0"
            ]
            
            for i, item in enumerate(score_items):
                text = small_font.render(item, True, self.colors['text'])
                self.screen.blit(text, (self.score_panel.x + 10, self.score_panel.y + 40 + i * 20))
            
            # Hokm indicator
            hokm_text = font.render("♠", True, self.colors['text_dark'])
            hokm_rect = hokm_text.get_rect(center=self.hokm_indicator.center)
            self.screen.blit(hokm_text, hokm_rect)
    
    def draw_sample_cards(self):
        """Draw some sample cards to show the layout in action."""
        # Sample cards in south (player's) hand
        sample_hand = ["A_of_hearts", "K_of_spades", "Q_of_diamonds", "J_of_clubs", "10_of_hearts"]
        
        south_area = self.player_areas['south']['rect']
        card_width, card_height = self.resources.get_card_dimensions()
        
        spacing = 60
        start_x = south_area.x + 50
        
        for i, card_name in enumerate(sample_hand):
            card_img = self.resources.get_card(card_name)
            if card_img:
                card_x = start_x + i * spacing
                card_y = south_area.y + 10
                self.screen.blit(card_img, (card_x, card_y))
        
        # Sample played cards
        played_cards = {
            'north': "9_of_hearts",
            'east': "J_of_diamonds",
            'south': "Q_of_clubs"
        }
        
        for position, card_name in played_cards.items():
            if position in self.played_positions:
                card_img = self.resources.get_card(card_name)
                if card_img:
                    x, y = self.played_positions[position]
                    self.screen.blit(card_img, (x, y))
    
    def run(self):
        """Main demo loop."""
        running = True
        show_cards = False
        
        while running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                elif event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        running = False
                    elif event.key == pygame.K_SPACE:
                        show_cards = not show_cards
            
            # Draw everything
            self.draw_table_surface()
            self.draw_player_areas()
            self.draw_play_area()
            self.draw_trick_pile()
            self.draw_ui_panels()
            
            if show_cards:
                self.draw_sample_cards()
            
            # Instructions
            font = self.resources.get_font("small")
            if font:
                instructions = [
                    "Hokm Game Table Layout Demo",
                    "Press SPACE to toggle sample cards",
                    "Press ESC to exit"
                ]
                
                for i, text in enumerate(instructions):
                    rendered = font.render(text, True, self.colors['text'])
                    self.screen.blit(rendered, (20, self.screen_height - 80 + i * 20))
            
            pygame.display.flip()
            self.clock.tick(60)
        
        pygame.quit()
        sys.exit()

def main():
    """Main function."""
    demo = HokmTableDemo()
    demo.run()

if __name__ == "__main__":
    main()
