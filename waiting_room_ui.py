#!/usr/bin/env python3
"""
Waiting Room UI for Hokm Game
Handles the pre-game waiting area where players gather before starting.
"""

import pygame
import time
from typing import List, Dict, Optional, Callable
from auth_ui import Button

class PlayerSlot:
    """Represents a player slot in the waiting room."""
    
    def __init__(self, x: int, y: int, width: int, height: int, position: str):
        self.rect = pygame.Rect(x, y, width, height)
        self.position = position  # "north", "east", "south", "west"
        self.player_name = ""
        self.is_ready = False
        self.is_host = False
        self.is_local_player = False
        self.avatar_id = 0
        
        # Visual states
        self.is_empty = True
        self.connection_status = "connected"  # connected, disconnected, joining
        
        # Colors
        self.bg_color_empty = (80, 80, 90)
        self.bg_color_occupied = (60, 90, 60)
        self.bg_color_ready = (60, 120, 60)
        self.bg_color_host = (90, 60, 90)
        self.border_color = (120, 120, 130)
        self.text_color = (255, 255, 255)
    
    def set_player(self, name: str, is_host: bool = False, is_local: bool = False):
        """Set player information for this slot."""
        self.player_name = name
        self.is_host = is_host
        self.is_local_player = is_local
        self.is_empty = False
        self.is_ready = False
    
    def clear_player(self):
        """Clear the player from this slot."""
        self.player_name = ""
        self.is_host = False
        self.is_local_player = False
        self.is_empty = True
        self.is_ready = False
        self.connection_status = "connected"
    
    def toggle_ready(self):
        """Toggle the ready state."""
        if not self.is_empty:
            self.is_ready = not self.is_ready
    
    def draw(self, surface, fonts):
        """Draw the player slot."""
        # Background color based on state
        if self.is_empty:
            bg_color = self.bg_color_empty
        elif self.is_host:
            bg_color = self.bg_color_host
        elif self.is_ready:
            bg_color = self.bg_color_ready
        else:
            bg_color = self.bg_color_occupied
        
        # Draw background
        pygame.draw.rect(surface, bg_color, self.rect)
        
        # Border (thicker for local player)
        border_width = 3 if self.is_local_player else 1
        pygame.draw.rect(surface, self.border_color, self.rect, border_width)
        
        medium_font = fonts.get('medium')
        small_font = fonts.get('small')
        
        if self.is_empty:
            # Empty slot
            if medium_font:
                empty_text = medium_font.render("Waiting for player...", True, (150, 150, 150))
                empty_rect = empty_text.get_rect(center=self.rect.center)
                surface.blit(empty_text, empty_rect)
            
            if small_font:
                position_text = small_font.render(f"Position: {self.position.title()}", True, (120, 120, 120))
                position_rect = position_text.get_rect(center=(self.rect.centerx, self.rect.bottom - 20))
                surface.blit(position_text, position_rect)
        else:
            # Occupied slot
            if medium_font:
                # Player name
                name_color = (255, 255, 100) if self.is_local_player else self.text_color
                name_text = medium_font.render(self.player_name, True, name_color)
                name_rect = name_text.get_rect(center=(self.rect.centerx, self.rect.y + 30))
                surface.blit(name_text, name_rect)
            
            if small_font:
                # Status indicators
                status_y = self.rect.y + 60
                
                # Host indicator
                if self.is_host:
                    host_text = small_font.render("👑 HOST", True, (255, 215, 0))
                    host_rect = host_text.get_rect(center=(self.rect.centerx, status_y))
                    surface.blit(host_text, host_rect)
                    status_y += 20
                
                # Ready indicator
                ready_color = (100, 255, 100) if self.is_ready else (255, 100, 100)
                ready_status = "READY" if self.is_ready else "NOT READY"
                ready_text = small_font.render(ready_status, True, ready_color)
                ready_rect = ready_text.get_rect(center=(self.rect.centerx, status_y))
                surface.blit(ready_text, ready_rect)
                
                # Connection status
                if self.connection_status != "connected":
                    conn_color = (255, 255, 100) if self.connection_status == "joining" else (255, 100, 100)
                    conn_text = small_font.render(self.connection_status.upper(), True, conn_color)
                    conn_rect = conn_text.get_rect(center=(self.rect.centerx, status_y + 20))
                    surface.blit(conn_text, conn_rect)

class ChatMessage:
    """Represents a chat message in the waiting room."""
    
    def __init__(self, sender: str, message: str, timestamp: float, msg_type: str = "normal"):
        self.sender = sender
        self.message = message
        self.timestamp = timestamp
        self.msg_type = msg_type  # normal, system, error
    
    def get_display_text(self) -> str:
        """Get formatted display text."""
        if self.msg_type == "system":
            return f"* {self.message}"
        else:
            return f"{self.sender}: {self.message}"
    
    def get_color(self) -> tuple:
        """Get color based on message type."""
        colors = {
            "normal": (255, 255, 255),
            "system": (200, 200, 255),
            "error": (255, 150, 150)
        }
        return colors.get(self.msg_type, (255, 255, 255))

class WaitingRoomScreen:
    """Waiting room screen where players gather before the game starts."""
    
    def __init__(self, screen_width: int, screen_height: int, room_name: str, 
                 player_name: str, is_host: bool,
                 ready_callback: Callable, leave_callback: Callable, 
                 start_callback: Callable, chat_callback: Callable):
        self.screen_width = screen_width
        self.screen_height = screen_height
        self.room_name = room_name
        self.player_name = player_name
        self.is_host = is_host
        self.ready_callback = ready_callback
        self.leave_callback = leave_callback
        self.start_callback = start_callback
        self.chat_callback = chat_callback
        
        # Game state
        self.players: Dict[str, Dict] = {}
        self.local_player_ready = False
        self.game_starting = False
        self.countdown_timer = 0
        
        # UI Layout
        header_height = 80
        footer_height = 100
        sidebar_width = 300
        
        self.header_rect = pygame.Rect(0, 0, screen_width, header_height)
        self.main_area_rect = pygame.Rect(0, header_height, screen_width - sidebar_width,
                                        screen_height - header_height - footer_height)
        self.chat_area_rect = pygame.Rect(screen_width - sidebar_width, header_height,
                                        sidebar_width, screen_height - header_height - footer_height)
        self.footer_rect = pygame.Rect(0, screen_height - footer_height, screen_width, footer_height)
        
        # Player slots (4 positions around a virtual table)
        slot_width = 200
        slot_height = 120
        center_x = self.main_area_rect.centerx
        center_y = self.main_area_rect.centery
        
        self.player_slots = {
            "north": PlayerSlot(center_x - slot_width // 2, center_y - 150, 
                              slot_width, slot_height, "north"),
            "east": PlayerSlot(center_x + 100, center_y - slot_height // 2,
                             slot_width, slot_height, "east"),
            "south": PlayerSlot(center_x - slot_width // 2, center_y + 50,
                              slot_width, slot_height, "south"),
            "west": PlayerSlot(center_x - 300, center_y - slot_height // 2,
                             slot_width, slot_height, "west")
        }
        
        # Set local player in south position
        self.player_slots["south"].set_player(player_name, is_host, True)
        
        # Chat
        self.chat_messages: List[ChatMessage] = []
        self.chat_scroll_offset = 0
        self.max_chat_messages = 100
        
        from auth_ui import InputField
        self.chat_input = InputField(
            self.chat_area_rect.x + 10, self.chat_area_rect.bottom - 40,
            self.chat_area_rect.width - 20, 30, "Type message..."
        )
        
        # Buttons
        button_width = 120
        button_height = 40
        button_spacing = 20
        
        self.ready_button = Button(
            self.footer_rect.x + 30, self.footer_rect.y + 20,
            button_width, button_height, "Ready", self.toggle_ready
        )
        
        self.leave_button = Button(
            self.footer_rect.x + 30 + button_width + button_spacing, self.footer_rect.y + 20,
            button_width, button_height, "Leave Room", self.leave_callback
        )
        
        # Host-only start button
        self.start_button = Button(
            self.footer_rect.right - button_width - 30, self.footer_rect.y + 20,
            button_width, button_height, "Start Game", self.attempt_start_game
        )
        
        # Colors
        self.bg_color = (40, 40, 50)
        self.header_color = (30, 30, 40)
        self.main_area_color = (50, 50, 60)
        self.chat_area_color = (45, 45, 55)
        self.footer_color = (30, 30, 40)
        self.text_color = (255, 255, 255)
        
        # Add initial system message
        self.add_system_message(f"Welcome to room '{room_name}'!")
        if is_host:
            self.add_system_message("You are the host. Click 'Start Game' when all players are ready.")
    
    def toggle_ready(self):
        """Toggle local player ready state."""
        self.local_player_ready = not self.local_player_ready
        self.player_slots["south"].toggle_ready()
        
        # Update button text
        self.ready_button.text = "Not Ready" if self.local_player_ready else "Ready"
        
        # Notify server
        self.ready_callback(self.local_player_ready)
    
    def attempt_start_game(self):
        """Attempt to start the game (host only)."""
        if not self.is_host:
            return
        
        # Check if all players are ready
        all_ready = True
        player_count = 0
        
        for slot in self.player_slots.values():
            if not slot.is_empty:
                player_count += 1
                if not slot.is_ready:
                    all_ready = False
                    break
        
        if player_count < 4:
            self.add_system_message("Need 4 players to start the game!")
            return
        
        if not all_ready:
            self.add_system_message("All players must be ready to start!")
            return
        
        # Start countdown
        self.game_starting = True
        self.countdown_timer = 5  # 5 second countdown
        self.start_callback()
    
    def add_player(self, player_name: str, position: str, is_host: bool = False):
        """Add a player to the waiting room."""
        if position in self.player_slots:
            self.player_slots[position].set_player(player_name, is_host)
            self.add_system_message(f"{player_name} joined the room")
    
    def remove_player(self, position: str):
        """Remove a player from the waiting room."""
        if position in self.player_slots and not self.player_slots[position].is_empty:
            player_name = self.player_slots[position].player_name
            self.player_slots[position].clear_player()
            self.add_system_message(f"{player_name} left the room")
    
    def update_player_ready(self, position: str, is_ready: bool):
        """Update a player's ready status."""
        if position in self.player_slots:
            self.player_slots[position].is_ready = is_ready
            status = "ready" if is_ready else "not ready"
            player_name = self.player_slots[position].player_name
            self.add_system_message(f"{player_name} is {status}")
    
    def add_chat_message(self, sender: str, message: str):
        """Add a chat message."""
        timestamp = time.time()
        chat_msg = ChatMessage(sender, message, timestamp)
        self.chat_messages.append(chat_msg)
        
        # Limit message history
        if len(self.chat_messages) > self.max_chat_messages:
            self.chat_messages.pop(0)
        
        # Auto-scroll to bottom
        self.chat_scroll_offset = max(0, len(self.chat_messages) * 25 - (self.chat_area_rect.height - 100))
    
    def add_system_message(self, message: str):
        """Add a system message."""
        timestamp = time.time()
        chat_msg = ChatMessage("System", message, timestamp, "system")
        self.chat_messages.append(chat_msg)
        
        if len(self.chat_messages) > self.max_chat_messages:
            self.chat_messages.pop(0)
        
        self.chat_scroll_offset = max(0, len(self.chat_messages) * 25 - (self.chat_area_rect.height - 100))
    
    def send_chat_message(self):
        """Send the typed chat message."""
        message = self.chat_input.text.strip()
        if message:
            self.chat_callback(message)
            self.add_chat_message(self.player_name, message)
            self.chat_input.text = ""
            self.chat_input.cursor_pos = 0
    
    def update(self, dt):
        """Update the waiting room state."""
        # Update chat input
        self.chat_input.update(dt)
        
        # Update countdown
        if self.game_starting and self.countdown_timer > 0:
            self.countdown_timer -= dt / 1000.0  # Convert to seconds
            if self.countdown_timer <= 0:
                self.countdown_timer = 0
    
    def handle_event(self, event):
        """Handle pygame events."""
        # Handle buttons
        self.ready_button.handle_event(event)
        self.leave_button.handle_event(event)
        if self.is_host:
            self.start_button.handle_event(event)
        
        # Handle chat input
        self.chat_input.handle_event(event)
        
        # Handle chat scrolling
        if event.type == pygame.MOUSEWHEEL:
            if self.chat_area_rect.collidepoint(pygame.mouse.get_pos()):
                scroll_speed = 30
                self.chat_scroll_offset -= event.y * scroll_speed
                max_scroll = max(0, len(self.chat_messages) * 25 - (self.chat_area_rect.height - 100))
                self.chat_scroll_offset = max(0, min(self.chat_scroll_offset, max_scroll))
        
        # Handle Enter key for chat
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_RETURN and self.chat_input.active:
                self.send_chat_message()
    
    def draw(self, surface, fonts):
        """Draw the waiting room screen."""
        # Background
        surface.fill(self.bg_color)
        
        # Header
        pygame.draw.rect(surface, self.header_color, self.header_rect)
        pygame.draw.line(surface, (100, 100, 110), 
                        (0, self.header_rect.bottom), 
                        (self.screen_width, self.header_rect.bottom), 2)
        
        # Main area
        pygame.draw.rect(surface, self.main_area_color, self.main_area_rect)
        
        # Chat area
        pygame.draw.rect(surface, self.chat_area_color, self.chat_area_rect)
        pygame.draw.line(surface, (100, 100, 110),
                        (self.chat_area_rect.left, self.chat_area_rect.top),
                        (self.chat_area_rect.left, self.chat_area_rect.bottom), 2)
        
        # Footer
        pygame.draw.rect(surface, self.footer_color, self.footer_rect)
        pygame.draw.line(surface, (100, 100, 110),
                        (0, self.footer_rect.top),
                        (self.screen_width, self.footer_rect.top), 2)
        
        # Draw sections
        self.draw_header(surface, fonts)
        self.draw_main_area(surface, fonts)
        self.draw_chat_area(surface, fonts)
        self.draw_footer(surface, fonts)
        
        # Draw countdown overlay if starting
        if self.game_starting and self.countdown_timer > 0:
            self.draw_countdown_overlay(surface, fonts)
    
    def draw_header(self, surface, fonts):
        """Draw the header section."""
        large_font = fonts.get('large')
        medium_font = fonts.get('medium')
        
        if large_font:
            title_text = large_font.render(f"Room: {self.room_name}", True, self.text_color)
            title_rect = title_text.get_rect(center=(self.screen_width // 2, 25))
            surface.blit(title_text, title_rect)
        
        if medium_font:
            # Player count
            occupied_slots = sum(1 for slot in self.player_slots.values() if not slot.is_empty)
            count_text = medium_font.render(f"Players: {occupied_slots}/4", True, (200, 255, 200))
            count_rect = count_text.get_rect(center=(self.screen_width // 2, 55))
            surface.blit(count_text, count_rect)
    
    def draw_main_area(self, surface, fonts):
        """Draw the main waiting area with player slots."""
        # Draw virtual table
        table_rect = pygame.Rect(self.main_area_rect.centerx - 150, 
                               self.main_area_rect.centery - 100,
                               300, 200)
        pygame.draw.ellipse(surface, (60, 40, 20), table_rect)
        pygame.draw.ellipse(surface, (100, 100, 110), table_rect, 3)
        
        # Draw player slots
        for slot in self.player_slots.values():
            slot.draw(surface, fonts)
        
        # Draw connection lines from table to slots
        small_font = fonts.get('small')
        if small_font:
            for position, slot in self.player_slots.items():
                if not slot.is_empty:
                    # Draw line from table edge to slot
                    if position == "north":
                        start_pos = (table_rect.centerx, table_rect.top)
                        end_pos = (slot.rect.centerx, slot.rect.bottom)
                    elif position == "south":
                        start_pos = (table_rect.centerx, table_rect.bottom)
                        end_pos = (slot.rect.centerx, slot.rect.top)
                    elif position == "east":
                        start_pos = (table_rect.right, table_rect.centery)
                        end_pos = (slot.rect.left, slot.rect.centery)
                    elif position == "west":
                        start_pos = (table_rect.left, table_rect.centery)
                        end_pos = (slot.rect.right, slot.rect.centery)
                    
                    pygame.draw.line(surface, (80, 80, 90), start_pos, end_pos, 2)
    
    def draw_chat_area(self, surface, fonts):
        """Draw the chat area."""
        small_font = fonts.get('small')
        medium_font = fonts.get('medium')
        
        # Chat title
        if medium_font:
            chat_title = medium_font.render("Chat", True, self.text_color)
            chat_title_rect = chat_title.get_rect()
            chat_title_rect.x = self.chat_area_rect.x + 10
            chat_title_rect.y = self.chat_area_rect.y + 10
            surface.blit(chat_title, chat_title_rect)
        
        # Chat messages
        if small_font:
            message_height = 25
            visible_messages = (self.chat_area_rect.height - 100) // message_height
            start_index = max(0, len(self.chat_messages) - visible_messages)
            
            for i, message in enumerate(self.chat_messages[start_index:]):
                y_pos = self.chat_area_rect.y + 40 + i * message_height - self.chat_scroll_offset % message_height
                
                if y_pos >= self.chat_area_rect.y + 40 and y_pos < self.chat_area_rect.bottom - 50:
                    msg_surface = small_font.render(
                        message.get_display_text()[:40] + ("..." if len(message.get_display_text()) > 40 else ""),
                        True, message.get_color()
                    )
                    msg_rect = msg_surface.get_rect()
                    msg_rect.x = self.chat_area_rect.x + 10
                    msg_rect.y = y_pos
                    
                    # Clip to chat area
                    clip_rect = self.chat_area_rect.copy()
                    clip_rect.height -= 60
                    surface.set_clip(clip_rect)
                    surface.blit(msg_surface, msg_rect)
                    surface.set_clip(None)
        
        # Chat input
        self.chat_input.draw(surface, small_font)
        
        # Instructions
        if small_font:
            instr_text = small_font.render("Press Enter to send", True, (150, 150, 150))
            instr_rect = instr_text.get_rect()
            instr_rect.x = self.chat_area_rect.x + 10
            instr_rect.y = self.chat_area_rect.bottom - 15
            surface.blit(instr_text, instr_rect)
    
    def draw_footer(self, surface, fonts):
        """Draw the footer with controls."""
        medium_font = fonts.get('medium')
        
        # Draw buttons
        if medium_font:
            self.ready_button.draw(surface, medium_font)
            self.leave_button.draw(surface, medium_font)
            
            if self.is_host:
                self.start_button.draw(surface, medium_font)
        
        # Status text
        small_font = fonts.get('small')
        if small_font:
            if self.is_host:
                status_text = "Host: All players must be ready to start"
                status_color = (255, 215, 0)
            else:
                status_text = "Waiting for host to start the game"
                status_color = (200, 200, 255)
            
            status_surface = small_font.render(status_text, True, status_color)
            status_rect = status_surface.get_rect(center=(self.screen_width // 2, self.footer_rect.y + 70))
            surface.blit(status_surface, status_rect)
    
    def draw_countdown_overlay(self, surface, fonts):
        """Draw game starting countdown overlay."""
        # Semi-transparent overlay
        overlay = pygame.Surface((self.screen_width, self.screen_height), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 180))
        surface.blit(overlay, (0, 0))
        
        # Countdown text
        large_font = fonts.get('large')
        if large_font:
            countdown_text = f"Game starting in {int(self.countdown_timer) + 1}..."
            countdown_surface = large_font.render(countdown_text, True, (255, 255, 100))
            countdown_rect = countdown_surface.get_rect(center=(self.screen_width // 2, self.screen_height // 2))
            surface.blit(countdown_surface, countdown_rect)
        
        # Progress bar
        bar_width = 400
        bar_height = 20
        bar_rect = pygame.Rect(self.screen_width // 2 - bar_width // 2, 
                             self.screen_height // 2 + 50, bar_width, bar_height)
        
        # Background
        pygame.draw.rect(surface, (100, 100, 100), bar_rect)
        
        # Progress
        progress = max(0, 1 - (self.countdown_timer / 5))
        progress_width = int(bar_width * progress)
        progress_rect = pygame.Rect(bar_rect.x, bar_rect.y, progress_width, bar_height)
        pygame.draw.rect(surface, (100, 255, 100), progress_rect)
        
        # Border
        pygame.draw.rect(surface, (200, 200, 200), bar_rect, 2)
