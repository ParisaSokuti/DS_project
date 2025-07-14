#!/usr/bin/env python3
"""
Pygame GUI Client for Hokm Game
Integrates with the existing WebSocket client to provide a visual interface.
Enhanced with authentication and lobby system.
"""

import pygame
import asyncio
import websockets
import json
import sys
import os
import threading
import queue
import time
from resources.game_resources import GameResources
from components.auth_ui import LoginScreen, RegisterScreen
from components.lobby_ui import LobbyScreen, GameRoom, CreateRoomDialog
from components.waiting_room_ui import WaitingRoomScreen
from typing import Dict, List, Optional, Tuple, Callable

# Initialize Pygame
pygame.init()

class HokmGameGUI:
    """Main GUI class for the Hokm game."""
    
    def __init__(self):
        # Screen settings
        self.screen_width = 1024
        self.screen_height = 768
        self.screen = pygame.display.set_mode((self.screen_width, self.screen_height))
        pygame.display.set_caption("Hokm Game - Enhanced Client")
        
        # Game resources
        self.resources = GameResources()
        self.resources.load_all_resources()
        
        # Clock for frame rate
        self.clock = pygame.time.Clock()
        self.fps = 60
        
        # Authentication state
        self.authenticated = False
        self.username = ""
        self.user_id = ""
        self.auth_token = ""
        
        # UI state management
        self.current_screen = "login"  # login, register, lobby, waiting_room, playing, game_over
        self.previous_screen = ""
        
        # Screen instances
        self.login_screen = None
        self.register_screen = None
        self.lobby_screen = None
        self.waiting_room_screen = None
        self.create_room_dialog = None
        
        # Current room info
        self.current_room_id = ""
        self.current_room_name = ""
        self.is_room_host = False
        
        # Game state
        self.game_state = "menu"  # menu, waiting, playing, game_over
        self.player_cards: List[str] = []
        self.table_cards: List[Tuple[str, str]] = []  # (card, player)
        self.current_player = ""
        self.hokm_suit = ""
        self.player_names = []
        self.teams = {}
        self.scores = {"team1": 0, "team2": 0}
        self.my_turn = False
        self.selected_card_index = -1
        
        # Enhanced game state tracking
        self.current_turn_player = ""
        self.game_phase = "waiting"  # waiting, dealing, hokm_selection, playing, trick_complete
        self.trick_number = 0
        self.round_number = 0
        self.waiting_for = ""  # What/who we're waiting for
        self.hokm_selector = ""  # Who is selecting hokm
        self.trick_winner = ""  # Who won the last trick
        
        # Drag and drop state
        self.dragging_card = False
        self.dragged_card_index = -1
        self.drag_offset = (0, 0)
        self.mouse_pos = (0, 0)
        self.hover_card_index = -1
        self.drag_start_pos = (0, 0)
        
        # UI elements
        self.buttons = {}
        self.card_positions = {}
        self.message_queue = queue.Queue()
        self.current_message = ""
        
        # UI update tracking for efficient redraws
        self.ui_update_flags = {
            'hand_cards': False,
            'table_cards': False,
            'status_panel': False,
            'player_areas': False,
            'scores': False,
            'message': False,
            'full_redraw': False
        }
        
        # Animation states for smooth transitions
        self.animations = {
            'card_play': {'active': False, 'start_time': 0, 'duration': 500},
            'trick_complete': {'active': False, 'start_time': 0, 'duration': 1000},
            'score_update': {'active': False, 'start_time': 0, 'duration': 800}
        }
        
        # WebSocket connection
        self.websocket = None
        self.websocket_thread = None
        
        # Initialize UI screens
        self.initialize_screens()
        
        # Colors
        self.colors = {
            'background': (0, 100, 0),
            'table': (0, 80, 0),
            'card_highlight': (255, 255, 0),
            'card_hover': (200, 200, 255),
            'card_playable': (100, 255, 100),
            'drag_drop_zone': (100, 255, 100),
            'text': (255, 255, 255),
            'text_dark': (0, 0, 0),
            'button': (100, 100, 100),
            'button_hover': (120, 120, 120),
            'button_pressed': (80, 80, 80)
        }
    
    def initialize_screens(self):
        """Initialize all UI screens."""
        # Login screen
        self.login_screen = LoginScreen(
            self.screen_width, self.screen_height,
            self.attempt_login, self.show_register_screen
        )
        
        # Register screen
        self.register_screen = RegisterScreen(
            self.screen_width, self.screen_height,
            self.attempt_register, self.show_login_screen
        )
        
        # Note: Lobby and waiting room screens will be initialized after authentication
    
    def show_login_screen(self):
        """Switch to login screen."""
        self.current_screen = "login"
    
    def show_register_screen(self):
        """Switch to register screen."""
        self.current_screen = "register"
    
    def show_lobby_screen(self):
        """Switch to lobby screen."""
        if not self.authenticated:
            self.show_login_screen()
            return
        
        self.current_screen = "lobby"
        if not self.lobby_screen:
            self.lobby_screen = LobbyScreen(
                self.screen_width, self.screen_height, self.username,
                self.show_create_room_dialog, self.join_room,
                self.refresh_room_list, self.logout
            )
    
    def show_waiting_room_screen(self, room_name: str, is_host: bool = False):
        """Switch to waiting room screen."""
        self.current_screen = "waiting_room"
        self.waiting_room_screen = WaitingRoomScreen(
            self.screen_width, self.screen_height, room_name, self.username, is_host,
            self.toggle_player_ready, self.leave_room, self.start_game, self.send_chat_message
        )
    
    def show_create_room_dialog(self):
        """Show create room dialog."""
        self.create_room_dialog = CreateRoomDialog(
            self.screen_width, self.screen_height,
            self.create_room, self.hide_create_room_dialog
        )
    
    def hide_create_room_dialog(self):
        """Hide create room dialog."""
        self.create_room_dialog = None
    
    # Authentication methods
    def attempt_login(self, username: str, password: str):
        """Attempt to log in with credentials."""
        print(f"Login attempt: {username}")
        
        # TODO: Implement actual authentication with server
        # For now, simulate successful login
        if len(username) >= 3 and len(password) >= 6:
            self.authenticated = True
            self.username = username
            self.user_id = f"user_{username}"
            self.auth_token = f"token_{username}_{int(time.time())}"
            
            self.login_screen.show_success("Login successful!")
            
            # Small delay for user to see success message
            def switch_to_lobby():
                time.sleep(1)
                self.show_lobby_screen()
                self.refresh_room_list()
            
            threading.Thread(target=switch_to_lobby, daemon=True).start()
        else:
            self.login_screen.show_error("Invalid username or password")
    
    def attempt_register(self, username: str, email: str, password: str):
        """Attempt to register new account."""
        print(f"Registration attempt: {username}, {email}")
        
        # TODO: Implement actual registration with server
        # For now, simulate successful registration
        self.register_screen.show_success("Registration successful! Please login.")
        
        # Switch to login screen after delay
        def switch_to_login():
            time.sleep(2)
            self.show_login_screen()
        
        threading.Thread(target=switch_to_login, daemon=True).start()
    
    def logout(self):
        """Log out and return to login screen."""
        self.authenticated = False
        self.username = ""
        self.user_id = ""
        self.auth_token = ""
        self.current_room_id = ""
        self.current_room_name = ""
        self.is_room_host = False
        
        # Clear screens
        self.lobby_screen = None
        self.waiting_room_screen = None
        
        self.show_login_screen()
    
    # Room management methods
    def refresh_room_list(self):
        """Refresh the list of available rooms."""
        if not self.lobby_screen:
            return
        
        print("Refreshing room list...")
        
        # TODO: Get actual room list from server
        # For now, create sample rooms
        sample_rooms = [
            GameRoom("room1", "Casual Game", ["Alice", "Bob"], 4, False),
            GameRoom("room2", "Pro Players Only", ["Charlie"], 4, False),
            GameRoom("room3", "Private Match", ["Dave", "Eve"], 4, True),
            GameRoom("room4", "Quick Game", ["Frank", "Grace", "Helen"], 4, False),
            GameRoom("room5", "Tournament Round 1", ["Ian", "Jack", "Kate", "Liam"], 4, False),
        ]
        
        # Set some rooms as playing
        sample_rooms[4].status = "playing"
        
        self.lobby_screen.update_rooms(sample_rooms)
    
    def create_room(self, room_name: str, is_private: bool, max_players: int):
        """Create a new game room."""
        print(f"Creating room: {room_name}, private: {is_private}")
        
        # TODO: Send create room request to server
        self.current_room_id = f"room_{int(time.time())}"
        self.current_room_name = room_name
        self.is_room_host = True
        
        self.hide_create_room_dialog()
        self.show_waiting_room_screen(room_name, True)
    
    def join_room(self, room_id: str):
        """Join an existing room."""
        print(f"Joining room: {room_id}")
        
        # TODO: Send join room request to server
        self.current_room_id = room_id
        self.current_room_name = f"Room {room_id}"
        self.is_room_host = False
        
        self.show_waiting_room_screen(self.current_room_name, False)
    
    def leave_room(self):
        """Leave the current room."""
        print("Leaving room")
        
        # TODO: Send leave room request to server
        self.current_room_id = ""
        self.current_room_name = ""
        self.is_room_host = False
        
        self.show_lobby_screen()
        self.refresh_room_list()
    
    def toggle_player_ready(self, is_ready: bool):
        """Toggle player ready status."""
        print(f"Player ready: {is_ready}")
        # TODO: Send ready status to server
    
    def start_game(self):
        """Start the game (host only)."""
        if not self.is_room_host:
            return
        
        print("Starting game...")
        # TODO: Send start game request to server
        
        # Simulate game start
        def start_game_sequence():
            time.sleep(3)  # Countdown time
            self.current_screen = "playing"
            self.game_state = "playing"
            
            # Initialize game state
            self.initialize_game_state()
        
        threading.Thread(target=start_game_sequence, daemon=True).start()
    
    def send_chat_message(self, message: str):
        """Send a chat message."""
        print(f"Chat: {message}")
        # TODO: Send chat message to server
    
    def initialize_game_state(self):
        """Initialize the game state when starting."""
        # Sample cards for testing
        sample_cards = [
            "A_of_hearts", "K_of_hearts", "Q_of_hearts", "J_of_hearts", "10_of_hearts",
            "9_of_spades", "8_of_spades", "7_of_spades", "6_of_spades", 
            "A_of_diamonds", "K_of_diamonds", "Q_of_clubs", "J_of_clubs"
        ]
        
        self.player_cards = sample_cards
        self.hokm_suit = "hearts"
        self.my_turn = True
        self.current_turn_player = "You"
        self.calculate_positions()
    
    def get_font_dict(self) -> Dict[str, pygame.font.Font]:
        """Get dictionary of fonts for UI rendering."""
        return {
            'small': self.resources.get_font('small'),
            'medium': self.resources.get_font('medium'), 
            'large': self.resources.get_font('large'),
            'title': self.resources.get_font('title')
        }
    
    def update(self):
        """Update game state and UI elements."""
        dt = self.clock.get_time()
        
        # Update current screen
        if self.current_screen == "login" and self.login_screen:
            self.login_screen.update(dt)
        elif self.current_screen == "register" and self.register_screen:
            self.register_screen.update(dt)
        elif self.current_screen == "waiting_room" and self.waiting_room_screen:
            self.waiting_room_screen.update(dt)
        elif self.current_screen == "playing":
            # Process game messages and update animations
            self.process_messages()
            self.update_animations()
    
    def draw(self):
        """Draw the current screen."""
        fonts = self.get_font_dict()
        
        if self.current_screen == "login" and self.login_screen:
            self.login_screen.draw(self.screen, fonts)
        elif self.current_screen == "register" and self.register_screen:
            self.register_screen.draw(self.screen, fonts)
        elif self.current_screen == "lobby" and self.lobby_screen:
            self.lobby_screen.draw(self.screen, fonts)
        elif self.current_screen == "waiting_room" and self.waiting_room_screen:
            self.waiting_room_screen.draw(self.screen, fonts)
        elif self.current_screen == "playing":
            self.draw_game_screen()
        
        # Draw create room dialog if active
        if self.create_room_dialog:
            self.create_room_dialog.draw(self.screen, fonts)
        
        pygame.display.flip()
    
    def draw_game_screen(self):
        """Draw the main game screen."""
        # Use existing game drawing methods
        self.draw_background()
        self.draw_player_names()
        self.draw_card_placeholders()
        self.draw_player_card_counts()
        self.draw_played_cards_placeholders()
        self.draw_trick_pile_placeholder()
        self.draw_cards_in_hand()
        self.draw_table_cards()
        self.draw_status_panel()
        self.draw_message()
    
    def handle_events(self) -> bool:
        """Handle pygame events. Returns False if should quit."""
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return False
            
            # Handle current screen events
            if self.current_screen == "login" and self.login_screen:
                self.login_screen.handle_event(event)
            elif self.current_screen == "register" and self.register_screen:
                self.register_screen.handle_event(event)
            elif self.current_screen == "lobby" and self.lobby_screen:
                self.lobby_screen.handle_event(event)
            elif self.current_screen == "waiting_room" and self.waiting_room_screen:
                self.waiting_room_screen.handle_event(event)
            elif self.current_screen == "playing":
                self.handle_game_events(event)
    
            # Handle create room dialog if active
            if self.create_room_dialog:
                self.create_room_dialog.handle_event(event)
        
        return True
    
    def handle_game_events(self, event):
        """Handle events during game play."""
        if event.type == pygame.MOUSEBUTTONDOWN:
            self.handle_mouse_down(event.pos, event.button)
        elif event.type == pygame.MOUSEBUTTONUP:
            self.handle_mouse_up(event.pos, event.button)
        elif event.type == pygame.MOUSEMOTION:
            self.handle_mouse_motion(event.pos)
        elif event.type == pygame.KEYDOWN:
            self.handle_key_input(event.key)
    
    def run(self):
        """Main game loop."""
        print("Starting Hokm Game Client...")
        print("Features:")
        print("• User Authentication (Login/Register)")
        print("• Lobby System with Room Browser")
        print("• Waiting Room with Chat")
        print("• Full Game Interface")
        
        running = True
        
        while running:
            running = self.handle_events()
            self.update()
            self.draw()
            # detect end of hand/game when playing and no cards left or game_state set to game_over
            if self.current_screen == "playing" and (self.game_state == "game_over" or not self.player_cards):
                # mark game over
                self.game_state = "game_over"
                # determine winner team by highest score
                winner = "Team 1" if self.scores["team1"] > self.scores["team2"] else "Team 2" if self.scores["team2"] > self.scores["team1"] else ""
                # show summary and handle choice
                choice = self.show_summary_screen(self.scores["team1"], self.scores["team2"], winner, is_game_over=True)
                if choice == 'play_again':
                    # reset for new hand
                    self.initialize_game_state()
                    self.game_state = "playing"
                elif choice == 'lobby':
                    # return to lobby
                    self.show_lobby_screen()
                else:
                    running = False
            self.clock.tick(self.fps)
        
        print("Game client shutting down...")
        pygame.quit()
    
    # Game methods (preserved from original implementation)
    def process_messages(self):
        """Process messages from WebSocket with enhanced state management."""
        messages_processed = 0
        max_messages_per_frame = 5
        
        try:
            while not self.message_queue.empty() and messages_processed < max_messages_per_frame:
                message = self.message_queue.get_nowait()
                messages_processed += 1
                
                print(f"📨 Processing message: {str(message)[:100]}...")
                
                # Handle different message types
                if isinstance(message, str):
                    self.update_game_state_from_message(message, None)
                elif isinstance(message, tuple) and len(message) >= 2:
                    msg_type, data = message[0], message[1]
                    self.update_game_state_from_message(msg_type, data)
                
        except queue.Empty:
            pass
    
    def update_game_state_from_message(self, msg_type, data):
        """Update game state based on server message."""
        if msg_type == "hand_update":
            self.player_cards = data if data else []
            self.trigger_ui_update('hand_cards')
        elif msg_type == "hokm_selected":
            self.hokm_suit = str(data)
            self.trigger_ui_update('status_panel')
        elif msg_type == "turn_change":
            self.current_turn_player = str(data)
            self.my_turn = (data == "You")
            self.trigger_ui_update('status_panel')
        elif msg_type == "card_played":
            if isinstance(data, tuple) and len(data) >= 2:
                card, player = data[0], data[1]
                self.table_cards.append((str(card), str(player)))
                self.trigger_ui_update('table_cards')
        elif msg_type == "trick_complete":
            self.table_cards.clear()
            self.trigger_ui_update('table_cards')
    
    def trigger_ui_update(self, element_type):
        """Mark UI elements for update."""
        if element_type in self.ui_update_flags:
            self.ui_update_flags[element_type] = True
    
    def update_animations(self):
        """Update animation states."""
        current_time = pygame.time.get_ticks()
        
        for anim_name, anim_data in self.animations.items():
            if anim_data['active']:
                elapsed = current_time - anim_data['start_time']
                if elapsed >= anim_data['duration']:
                    anim_data['active'] = False
    
    def calculate_positions(self):
        """Calculate UI element positions (preserved method)."""
        # Card dimensions
        card_width, card_height = 71, 96
        
        # Player hand area (bottom)
        hand_width = 600
        hand_height = 120
        self.player_areas = {
            'south': pygame.Rect(
                (self.screen_width - hand_width) // 2,
                self.screen_height - hand_height - 20,
                hand_width, hand_height
            )
        }
        
        # Table area (center)
        table_width = 400
        table_height = 300
        self.table_area = pygame.Rect(
            (self.screen_width - table_width) // 2,
            (self.screen_height - table_height) // 2,
            table_width, table_height
        )
        
        # Card positions for played cards
        self.played_card_positions = {
            'north': (self.table_area.centerx - card_width // 2, self.table_area.y + 20),
            'east': (self.table_area.right - card_width - 20, self.table_area.centery - card_height // 2),
            'south': (self.table_area.centerx - card_width // 2, self.table_area.bottom - card_height - 20),
            'west': (self.table_area.x + 20, self.table_area.centery - card_height // 2)
        }
        
        # Status panel area
        self.status_panel_area = pygame.Rect(
            self.screen_width - 250 - 10,
            self.screen_height // 2 - 150,
            250, 300
        )
        
        # Message area
        self.message_area = pygame.Rect(20, 20, 400, 60)
        
        # Initialize card positions dict
        self.card_positions = {}
    
    def draw_background(self):
        """Draw game background."""
        self.screen.fill((0, 100, 0))
        
        # Draw table
        pygame.draw.ellipse(self.screen, (0, 80, 0), self.table_area)
        pygame.draw.ellipse(self.screen, (0, 0, 0), self.table_area, 3)
    
    def draw_player_names(self):
        """Draw placeholder player names."""
        font = self.resources.get_font("medium")
        if not font:
            return
        
        positions = ["North", "East", "South (You)", "West"]
        colors = [(200, 200, 200), (200, 200, 200), (255, 255, 100), (200, 200, 200)]
        
        y_positions = [50, self.screen_height // 2, self.screen_height - 150, self.screen_height // 2]
        x_positions = [self.screen_width // 2, self.screen_width - 100, self.screen_width // 2, 100]
        
        for i, (name, color) in enumerate(zip(positions, colors)):
            text = font.render(name, True, color)
            text_rect = text.get_rect(center=(x_positions[i], y_positions[i]))
            self.screen.blit(text, text_rect)
    
    def draw_card_placeholders(self):
        """Draw card back placeholders for other players."""
        # Simple placeholders - just rectangles
        card_width, card_height = 71, 96
        
        # North player cards
        for i in range(5):
            x = self.screen_width // 2 - 150 + i * 30
            y = 80
            rect = pygame.Rect(x, y, card_width - 10, card_height - 10)
            pygame.draw.rect(self.screen, (100, 100, 150), rect)
            pygame.draw.rect(self.screen, (0, 0, 0), rect, 1)
    
    def draw_player_card_counts(self):
        """Draw card counts for each player."""
        font = self.resources.get_font("small")
        if not font:
            return
        
        # Show card counts
        counts = [f"Cards: 13", f"Cards: 13", f"Cards: {len(self.player_cards)}", f"Cards: 13"]
        positions = [(self.screen_width // 2, 130), (self.screen_width - 50, self.screen_height // 2 + 50),
                    (self.screen_width // 2, self.screen_height - 100), (50, self.screen_height // 2 + 50)]
        
        for count, pos in zip(counts, positions):
            text = font.render(count, True, (200, 200, 200))
            text_rect = text.get_rect(center=pos)
            self.screen.blit(text, text_rect)
    
    def draw_played_cards_placeholders(self):
        """Draw placeholders for played cards."""
        card_width, card_height = 71, 96
        
        for position, (x, y) in self.played_card_positions.items():
            rect = pygame.Rect(x, y, card_width, card_height)
            pygame.draw.rect(self.screen, (80, 80, 80), rect, 2)
    
    def draw_trick_pile_placeholder(self):
        """Draw trick pile placeholder."""
        font = self.resources.get_font("small")
        if font:
            text = font.render("Tricks: 0", True, (255, 255, 255))
            text_rect = text.get_rect(center=(100, 150))
            self.screen.blit(text, text_rect)
    
    def draw_cards_in_hand(self):
        """Draw player's hand cards."""
        if not self.player_cards:
            return
        
        card_width, card_height = 71, 96
        hand_area = self.player_areas['south']
        
        # Calculate spacing
        num_cards = len(self.player_cards)
        if num_cards == 0:
            return
        
        spacing = min(80, (hand_area.width - card_width) // max(1, num_cards - 1))
        total_width = (num_cards - 1) * spacing + card_width
        start_x = hand_area.x + (hand_area.width - total_width) // 2
        card_y = hand_area.y + (hand_area.height - card_height) // 2
        
        self.card_positions.clear()
        
        for i, card_name in enumerate(self.player_cards):
            card_x = start_x + i * spacing
            card_rect = pygame.Rect(card_x, card_y, card_width, card_height)
            
            # Draw card
            card_img = self.resources.get_card(card_name)
            if card_img:
                self.screen.blit(card_img, card_rect)
            else:
                # Draw placeholder
                pygame.draw.rect(self.screen, (200, 200, 200), card_rect)
                pygame.draw.rect(self.screen, (0, 0, 0), card_rect, 1)
                
                # Draw card name
                font = self.resources.get_font("small")
                if font:
                    text = font.render(card_name[:5], True, (0, 0, 0))
                    text_rect = text.get_rect(center=card_rect.center)
                    self.screen.blit(text, text_rect)
            
            # Store position for click detection
            self.card_positions[i] = card_rect
            
            # Highlight selected card
            if i == self.selected_card_index:
                pygame.draw.rect(self.screen, (255, 255, 0), card_rect, 3)
    
    def draw_table_cards(self):
        """Draw cards played on the table."""
        if not self.table_cards:
            return
        
        card_width, card_height = 71, 96
        
        for card_name, player in self.table_cards:
            # Simple positioning - just center them
            position = "south"  # Default position
            if position in self.played_card_positions:
                x, y = self.played_card_positions[position]
                card_rect = pygame.Rect(x, y, card_width, card_height)
                
                card_img = self.resources.get_card(card_name)
                if card_img:
                    self.screen.blit(card_img, card_rect)
                else:
                    # Draw placeholder
                    pygame.draw.rect(self.screen, (200, 200, 200), card_rect)
                    pygame.draw.rect(self.screen, (0, 0, 0), card_rect, 1)
    
    def draw_status_panel(self):
        """Draw status panel with game information."""
        # Panel background
        pygame.draw.rect(self.screen, (50, 50, 60), self.status_panel_area)
        pygame.draw.rect(self.screen, (100, 100, 110), self.status_panel_area, 2)
        
        font = self.resources.get_font("medium")
        small_font = self.resources.get_font("small")
        
        if font:
            # Title
            title_text = font.render("Game Status", True, (255, 255, 255))
            title_rect = title_text.get_rect(centerx=self.status_panel_area.centerx, 
                                             top=self.status_panel_area.y + 25)
            self.screen.blit(title_text, title_rect)
        
        if small_font:
            y_offset = 60
            
            # Turn
            turn_text = f"Turn: {self.current_turn_player}" if hasattr(self, 'current_turn_player') else "Turn: Waiting"
            turn_color = (100, 255, 100) if getattr(self, 'my_turn', False) else (255, 255, 255)
            text = small_font.render(turn_text, True, turn_color)
            text_rect = text.get_rect(centerx=self.status_panel_area.centerx, 
                                      top=self.status_panel_area.y + y_offset)
            self.screen.blit(text, text_rect)
            y_offset += 30
            
            # Hokm
            hokm_text = f"Hokm: {self.hokm_suit.title()}" if self.hokm_suit else "Hokm: Not selected"
            text = small_font.render(hokm_text, True, (255, 200, 100))
            text_rect = text.get_rect(centerx=self.status_panel_area.centerx, 
                                      top=self.status_panel_area.y + y_offset)
            self.screen.blit(text, text_rect)
            y_offset += 40
            
            # Scores
            score_text = f"Team 1: {self.scores['team1']}  Team 2: {self.scores['team2']}"
            text = small_font.render(score_text, True, (200, 255, 200))
            text_rect = text.get_rect(centerx=self.status_panel_area.centerx, 
                                      top=self.status_panel_area.y + y_offset)
            self.screen.blit(text, text_rect)
    
    def draw_message(self):
        """Draw current message."""
        if not hasattr(self, 'current_message') or not self.current_message:
            return
        
        pygame.draw.rect(self.screen, (100, 100, 100), self.message_area)
        pygame.draw.rect(self.screen, (0, 0, 0), self.message_area, 2)
        
        font = self.resources.get_font("medium")
        if font:
            text = font.render(self.current_message, True, (0, 0, 0))
            text_rect = text.get_rect(center=self.message_area.center)
            self.screen.blit(text, text_rect)
    
    def draw_button(self, surface, rect, text, font=None, is_selected=False, colors=None):
        """
        Draw a reusable button with centered text and optional highlight.
        
        Args:
            surface: The pygame surface to draw on
            rect: The button rectangle (pygame.Rect)
            text: The button text to display
            font: The font to use for the text (optional, uses medium font if None)
            is_selected: Whether the button is selected/highlighted
            colors: Dictionary with color overrides (optional)
        """
        if font is None:
            font = self.resources.get_font("medium")
        
        if colors is None:
            colors = {
                'normal': self.colors['button'],
                'selected': self.colors['button_hover'],
                'border': (200, 200, 100),
                'text': self.colors['text']
            }
        
        # Button background and border
        bg_color = colors['selected'] if is_selected else colors['normal']
        pygame.draw.rect(surface, bg_color, rect)
        pygame.draw.rect(surface, colors['border'], rect, 2)
        
        # Button text centered
        if font:
            txt_surf = font.render(text, True, colors['text'])
            txt_rect = txt_surf.get_rect(center=rect.center)
            surface.blit(txt_surf, txt_rect)
    
    def handle_mouse_down(self, pos, button):
        """Handle mouse button down events."""
        if button == 1 and self.my_turn:  # Left click
            self.handle_card_click(pos)
    
    def handle_mouse_up(self, pos, button):
        """Handle mouse button up events."""
        pass
    
    def handle_mouse_motion(self, pos):
        """Handle mouse motion events."""
        pass
    
    def handle_key_input(self, key):
        """Handle keyboard input."""
        if key == pygame.K_ESCAPE:
            # Return to lobby
            self.show_lobby_screen()
    
    def handle_card_click(self, pos):
        """Handle clicking on a card."""
        if not self.my_turn:
            return
        
        for card_index, card_rect in self.card_positions.items():
            if card_rect.collidepoint(pos):
                if self.selected_card_index == card_index:
                    # Play the card
                    self.play_card(card_index)
                else:
                    # Select the card
                    self.selected_card_index = card_index
                    if hasattr(self, 'current_message'):
                        self.current_message = f"Selected: {self.player_cards[card_index]}"
                break
    
    def play_card(self, card_index):
        """Play a card from the hand."""
        if 0 <= card_index < len(self.player_cards):
            card_name = self.player_cards[card_index]
            
            # Add to played cards
            self.table_cards.append((card_name, "You"))
            
            # Remove from hand
            self.player_cards.pop(card_index)
            
            # Clear selection
            self.selected_card_index = -1
            self.my_turn = False
            
            if hasattr(self, 'current_message'):
                self.current_message = f"You played {card_name}"
            
            print(f"Played card: {card_name}")

    def show_summary_screen(self, team1_score: int, team2_score: int, winner: str, is_game_over: bool):
        """
        Show game summary screen with scores and navigation options.
        
        Args:
            team1_score: Score for Team 1
            team2_score: Score for Team 2
            winner: String indicating which team won
            is_game_over: Boolean indicating if the entire game is over
            
        Returns:
            String: 'play_again', 'lobby', or None if window closed
        """
        # Save previous screen state
        prev_screen = self.current_screen
        
        # Setup colors
        bg_color = (0, 80, 0)  # Dark green background
        panel_color = (50, 50, 60)  # Dark panel
        border_color = (200, 200, 100)  # Gold border
        text_color = (255, 255, 255)  # White text
        highlight_color = (255, 255, 100)  # Yellow highlight
        
        # Button colors
        button_colors = {
            'normal': (100, 100, 150),
            'hover': (120, 120, 200),
            'text': (255, 255, 255)
        }
        
        # Get fonts
        fonts = self.get_font_dict()
        title_font = fonts['title'] if 'title' in fonts else fonts['large']
        large_font = fonts['large']
        medium_font = fonts['medium']
        
        # Create summary panel
        panel_width, panel_height = 500, 400
        panel_rect = pygame.Rect(
            (self.screen_width - panel_width) // 2,
            (self.screen_height - panel_height) // 2,
            panel_width, panel_height
        )
        
        # Create buttons
        button_width, button_height = 200, 50
        button_margin = 20
        play_again_rect = pygame.Rect(
            panel_rect.centerx - button_width - button_margin,
            panel_rect.bottom - button_height - 40,
            button_width, button_height
        )
        lobby_rect = pygame.Rect(
            panel_rect.centerx + button_margin,
            panel_rect.bottom - button_height - 40,
            button_width, button_height
        )
        
        # Function to draw the screen
        def draw_summary():
            # Fill the screen with background color
            self.screen.fill(bg_color)
            
            # Draw centered panel
            pygame.draw.rect(self.screen, panel_color, panel_rect)
            pygame.draw.rect(self.screen, border_color, panel_rect, 4)
            
            # Draw title - 'Hand Over!' or 'Game Over!'
            title_text = "Hand Over!" if not is_game_over else "Game Over!"
            title_surface = title_font.render(title_text, True, text_color)
            title_rect = title_surface.get_rect(centerx=panel_rect.centerx, top=panel_rect.top + 30)
            self.screen.blit(title_surface, title_rect)
            
            # Draw scores in center - 'Team 1: X   Team 2: Y'
            y_offset = title_rect.bottom + 40
            scores_text = f"Team 1: {team1_score}   Team 2: {team2_score}"
            scores_surface = large_font.render(scores_text, True, text_color)
            scores_rect = scores_surface.get_rect(centerx=panel_rect.centerx, top=y_offset)
            self.screen.blit(scores_surface, scores_rect)
            
            # Draw winner announcement below scores
            winner_text = f"Winner: {winner}" if winner else "It's a Tie!"
            winner_surface = large_font.render(winner_text, True, highlight_color)
            winner_rect = winner_surface.get_rect(centerx=panel_rect.centerx, top=scores_rect.bottom + 30)
            self.screen.blit(winner_surface, winner_rect)
            
            # Draw buttons
            mouse_pos = pygame.mouse.get_pos()
            
            # Play Again button
            self.draw_button(
                self.screen, play_again_rect, "Play Again", medium_font,
                is_selected=play_again_rect.collidepoint(mouse_pos),
                colors={'normal': button_colors['normal'],
                        'selected': button_colors['hover'],
                        'border': border_color,
                        'text': button_colors['text']}
            )
            
            # Return to Lobby button
            self.draw_button(
                self.screen, lobby_rect, "Return to Lobby", medium_font,
                is_selected=lobby_rect.collidepoint(mouse_pos),
                colors={'normal': button_colors['normal'],
                        'selected': button_colors['hover'],
                        'border': border_color,
                        'text': button_colors['text']}
            )
            
            # Update display
            pygame.display.flip()
        
        # Event loop
        running = True
        result = None
        
        while running:
            draw_summary()
            
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                    result = None
                elif event.type == pygame.MOUSEBUTTONDOWN:
                    if event.button == 1:  # Left click
                        if play_again_rect.collidepoint(event.pos):
                            running = False
                            result = 'play_again'
                        elif lobby_rect.collidepoint(event.pos):
                            running = False
                            result = 'lobby'
            
            self.clock.tick(30)
        
        # Restore previous screen state
        self.current_screen = prev_screen
        
        return result
def main():
    """Run the enhanced Hokm game client."""
    try:
        game = HokmGameGUI()
        game.run()
    except Exception as e:
        print(f"Error running game: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
