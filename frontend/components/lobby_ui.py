#!/usr/bin/env python3
"""
Lobby UI Components for Hokm Game
Handles room listing, creation, and waiting areas.
"""

import pygame
import time
from typing import List, Dict, Optional, Callable
from .auth_ui import Button

class GameRoom:
    """Represents a game room in the lobby."""
    
    def __init__(self, room_id: str, name: str, players: List[str], 
                 max_players: int = 4, is_private: bool = False):
        self.room_id = room_id
        self.name = name
        self.players = players
        self.max_players = max_players
        self.is_private = is_private
        self.created_time = time.time()
        self.status = "waiting"  # waiting, playing, finished
    
    def is_full(self) -> bool:
        """Check if the room is full."""
        return len(self.players) >= self.max_players
    
    def can_join(self) -> bool:
        """Check if the room can be joined."""
        return not self.is_full() and self.status == "waiting"
    
    def get_status_text(self) -> str:
        """Get formatted status text."""
        if self.status == "playing":
            return "In Game"
        elif self.is_full():
            return "Full"
        else:
            return f"{len(self.players)}/{self.max_players}"

class RoomListItem:
    """Visual representation of a room in the lobby list."""
    
    def __init__(self, x: int, y: int, width: int, height: int, room: GameRoom,
                 join_callback: Callable, spectate_callback: Callable = None):
        self.rect = pygame.Rect(x, y, width, height)
        self.room = room
        self.join_callback = join_callback
        self.spectate_callback = spectate_callback
        self.hovered = False
        
        # Create join button
        button_width = 80
        button_height = 30
        self.join_button = Button(
            x + width - button_width - 10,
            y + (height - button_height) // 2,
            button_width, button_height,
            "Join" if room.can_join() else "Spectate",
            self.on_join_click
        )
        
        # Colors
        self.bg_color = (70, 70, 80)
        self.bg_color_hover = (85, 85, 95)
        self.border_color = (100, 100, 110)
        self.text_color = (255, 255, 255)
        self.status_colors = {
            "waiting": (100, 255, 100),
            "playing": (255, 255, 100),
            "full": (255, 100, 100)
        }
    
    def on_join_click(self):
        """Handle join button click."""
        if self.room.can_join():
            self.join_callback(self.room.room_id)
        elif self.spectate_callback:
            self.spectate_callback(self.room.room_id)
    
    def handle_event(self, event):
        """Handle pygame events."""
        if event.type == pygame.MOUSEMOTION:
            self.hovered = self.rect.collidepoint(event.pos)
        
        self.join_button.handle_event(event)
    
    def draw(self, surface, fonts):
        """Draw the room list item."""
        # Background
        bg_color = self.bg_color_hover if self.hovered else self.bg_color
        pygame.draw.rect(surface, bg_color, self.rect)
        pygame.draw.rect(surface, self.border_color, self.rect, 1)
        
        # Room name
        medium_font = fonts.get('medium')
        small_font = fonts.get('small')
        
        if medium_font:
            name_text = medium_font.render(self.room.name, True, self.text_color)
            name_rect = name_text.get_rect()
            name_rect.x = self.rect.x + 15
            name_rect.y = self.rect.y + 8
            surface.blit(name_text, name_rect)
        
        # Player list
        if small_font:
            players_text = "Players: " + ", ".join(self.room.players) if self.room.players else "No players"
            if len(players_text) > 50:  # Truncate if too long
                players_text = players_text[:47] + "..."
            
            players_surface = small_font.render(players_text, True, (200, 200, 200))
            players_rect = players_surface.get_rect()
            players_rect.x = self.rect.x + 15
            players_rect.y = self.rect.y + 35
            surface.blit(players_surface, players_rect)
        
        # Status
        if small_font:
            status_text = self.room.get_status_text()
            status_color = self.status_colors.get(
                "full" if self.room.is_full() else self.room.status,
                (200, 200, 200)
            )
            
            status_surface = small_font.render(status_text, True, status_color)
            status_rect = status_surface.get_rect()
            status_rect.x = self.rect.x + 15
            status_rect.y = self.rect.y + 55
            surface.blit(status_surface, status_rect)
        
        # Private room indicator
        if self.room.is_private:
            lock_text = "🔒"
            if medium_font:
                lock_surface = medium_font.render(lock_text, True, (255, 255, 100))
                lock_rect = lock_surface.get_rect()
                lock_rect.x = self.rect.right - 120
                lock_rect.y = self.rect.y + 8
                surface.blit(lock_surface, lock_rect)
        
        # Draw join button
        if medium_font:
            self.join_button.draw(surface, medium_font)

class LobbyScreen:
    """Main lobby screen showing available rooms."""
    
    def __init__(self, screen_width: int, screen_height: int, username: str,
                 create_room_callback: Callable, join_room_callback: Callable,
                 refresh_callback: Callable, logout_callback: Callable):
        self.screen_width = screen_width
        self.screen_height = screen_height
        self.username = username
        self.create_room_callback = create_room_callback
        self.join_room_callback = join_room_callback
        self.refresh_callback = refresh_callback
        self.logout_callback = logout_callback
        
        # Room list
        self.rooms: List[GameRoom] = []
        self.room_list_items: List[RoomListItem] = []
        self.scroll_offset = 0
        self.max_visible_rooms = 8
        
        # UI areas
        header_height = 100
        footer_height = 80
        sidebar_width = 250
        
        self.header_rect = pygame.Rect(0, 0, screen_width, header_height)
        self.sidebar_rect = pygame.Rect(0, header_height, sidebar_width, 
                                      screen_height - header_height - footer_height)
        self.room_list_rect = pygame.Rect(sidebar_width, header_height, 
                                        screen_width - sidebar_width, 
                                        screen_height - header_height - footer_height)
        self.footer_rect = pygame.Rect(0, screen_height - footer_height, 
                                     screen_width, footer_height)
        
        # Buttons
        button_width = 180
        button_height = 40
        button_spacing = 15
        
        sidebar_center_x = self.sidebar_rect.centerx
        button_start_y = self.sidebar_rect.y + 30
        
        self.create_room_button = Button(
            sidebar_center_x - button_width // 2, button_start_y,
            button_width, button_height, "Create Room", self.create_room_callback
        )
        
        self.refresh_button = Button(
            sidebar_center_x - button_width // 2, button_start_y + button_height + button_spacing,
            button_width, button_height, "Refresh List", self.refresh_callback
        )
        
        self.logout_button = Button(
            sidebar_center_x - button_width // 2, 
            self.sidebar_rect.bottom - button_height - 20,
            button_width, button_height, "Logout", self.logout_callback
        )
        
        # Status
        self.status_message = ""
        self.last_refresh_time = 0
        
        # Colors
        self.bg_color = (35, 35, 45)
        self.header_color = (25, 25, 35)
        self.sidebar_color = (45, 45, 55)
        self.room_list_color = (55, 55, 65)
        self.footer_color = (25, 25, 35)
        self.text_color = (255, 255, 255)
    
    def update_rooms(self, rooms: List[GameRoom]):
        """Update the list of available rooms."""
        self.rooms = rooms
        self.last_refresh_time = time.time()
        
        # Recreate room list items
        self.room_list_items.clear()
        
        item_height = 90
        item_spacing = 5
        item_width = self.room_list_rect.width - 40
        
        for i, room in enumerate(rooms):
            y_pos = self.room_list_rect.y + 20 + i * (item_height + item_spacing) - self.scroll_offset
            
            if y_pos + item_height > self.room_list_rect.y and y_pos < self.room_list_rect.bottom:
                item = RoomListItem(
                    self.room_list_rect.x + 20, y_pos,
                    item_width, item_height, room,
                    self.join_room_callback
                )
                self.room_list_items.append(item)
    
    def handle_scroll(self, direction: int):
        """Handle scrolling through the room list."""
        scroll_speed = 30
        max_scroll = max(0, len(self.rooms) * 95 - self.room_list_rect.height + 40)
        
        self.scroll_offset += direction * scroll_speed
        self.scroll_offset = max(0, min(self.scroll_offset, max_scroll))
        
        # Update room list items after scrolling
        if self.rooms:
            self.update_rooms(self.rooms)
    
    def handle_event(self, event):
        """Handle pygame events."""
        # Handle button clicks
        self.create_room_button.handle_event(event)
        self.refresh_button.handle_event(event)
        self.logout_button.handle_event(event)
        
        # Handle room list item events
        for item in self.room_list_items:
            item.handle_event(event)
        
        # Handle scrolling
        if event.type == pygame.MOUSEWHEEL:
            if self.room_list_rect.collidepoint(pygame.mouse.get_pos()):
                self.handle_scroll(-event.y)
    
    def draw(self, surface, fonts):
        """Draw the lobby screen."""
        # Background
        surface.fill(self.bg_color)
        
        # Header
        pygame.draw.rect(surface, self.header_color, self.header_rect)
        pygame.draw.line(surface, (100, 100, 110), 
                        (0, self.header_rect.bottom), 
                        (self.screen_width, self.header_rect.bottom), 2)
        
        # Sidebar
        pygame.draw.rect(surface, self.sidebar_color, self.sidebar_rect)
        pygame.draw.line(surface, (100, 100, 110),
                        (self.sidebar_rect.right, self.sidebar_rect.top),
                        (self.sidebar_rect.right, self.sidebar_rect.bottom), 2)
        
        # Room list area
        pygame.draw.rect(surface, self.room_list_color, self.room_list_rect)
        
        # Footer
        pygame.draw.rect(surface, self.footer_color, self.footer_rect)
        pygame.draw.line(surface, (100, 100, 110),
                        (0, self.footer_rect.top),
                        (self.screen_width, self.footer_rect.top), 2)
        
        # Header content
        self.draw_header(surface, fonts)
        
        # Sidebar content
        self.draw_sidebar(surface, fonts)
        
        # Room list content
        self.draw_room_list(surface, fonts)
        
        # Footer content
        self.draw_footer(surface, fonts)
    
    def draw_header(self, surface, fonts):
        """Draw the header section."""
        large_font = fonts.get('large')
        medium_font = fonts.get('medium')
        
        if large_font:
            title_text = large_font.render("Hokm Game Lobby", True, self.text_color)
            title_rect = title_text.get_rect(center=(self.screen_width // 2, 35))
            surface.blit(title_text, title_rect)
        
        if medium_font:
            welcome_text = medium_font.render(f"Welcome, {self.username}!", True, (200, 255, 200))
            welcome_rect = welcome_text.get_rect(center=(self.screen_width // 2, 70))
            surface.blit(welcome_text, welcome_rect)
    
    def draw_sidebar(self, surface, fonts):
        """Draw the sidebar with controls."""
        medium_font = fonts.get('medium')
        small_font = fonts.get('small')
        
        # Section title
        if medium_font:
            controls_text = medium_font.render("Controls", True, self.text_color)
            controls_rect = controls_text.get_rect(center=(self.sidebar_rect.centerx, 
                                                         self.sidebar_rect.y + 15))
            surface.blit(controls_text, controls_rect)
        
        # Draw buttons
        if medium_font:
            self.create_room_button.draw(surface, medium_font)
            self.refresh_button.draw(surface, medium_font)
            self.logout_button.draw(surface, medium_font)
        
        # Player count
        if small_font:
            online_text = f"Players Online: {len(self.rooms) * 2}"  # Rough estimate
            online_surface = small_font.render(online_text, True, (200, 200, 255))
            online_rect = online_surface.get_rect(center=(self.sidebar_rect.centerx,
                                                        self.sidebar_rect.bottom - 60))
            surface.blit(online_surface, online_rect)
    
    def draw_room_list(self, surface, fonts):
        """Draw the list of available rooms."""
        medium_font = fonts.get('medium')
        small_font = fonts.get('small')
        
        # Section title
        if medium_font:
            rooms_text = medium_font.render("Available Rooms", True, self.text_color)
            rooms_rect = rooms_text.get_rect()
            rooms_rect.x = self.room_list_rect.x + 20
            rooms_rect.y = self.room_list_rect.y + 10
            surface.blit(rooms_text, rooms_rect)
        
        # Room count
        if small_font:
            count_text = f"({len(self.rooms)} rooms found)"
            count_surface = small_font.render(count_text, True, (180, 180, 180))
            count_rect = count_surface.get_rect()
            count_rect.x = rooms_rect.right + 10
            count_rect.y = self.room_list_rect.y + 15
            surface.blit(count_surface, count_rect)
        
        # Draw room items
        for item in self.room_list_items:
            item.draw(surface, fonts)
        
        # Empty state
        if not self.rooms:
            if medium_font:
                empty_text = "No rooms available"
                empty_surface = medium_font.render(empty_text, True, (150, 150, 150))
                empty_rect = empty_surface.get_rect(center=self.room_list_rect.center)
                surface.blit(empty_surface, empty_rect)
                
                if small_font:
                    hint_text = "Create a new room to start playing!"
                    hint_surface = small_font.render(hint_text, True, (120, 120, 120))
                    hint_rect = hint_surface.get_rect(center=(self.room_list_rect.centerx,
                                                            self.room_list_rect.centery + 30))
                    surface.blit(hint_surface, hint_rect)
        
        # Scroll indicator
        if len(self.rooms) > self.max_visible_rooms:
            self.draw_scroll_indicator(surface)
    
    def draw_scroll_indicator(self, surface):
        """Draw scroll indicator on the right side."""
        indicator_width = 6
        indicator_rect = pygame.Rect(
            self.room_list_rect.right - indicator_width - 5,
            self.room_list_rect.y + 50,
            indicator_width,
            self.room_list_rect.height - 100
        )
        
        # Background
        pygame.draw.rect(surface, (80, 80, 80), indicator_rect)
        
        # Thumb
        total_content_height = len(self.rooms) * 95
        visible_height = self.room_list_rect.height - 100
        
        if total_content_height > visible_height:
            thumb_height = max(20, int(visible_height * visible_height / total_content_height))
            thumb_y = indicator_rect.y + int(self.scroll_offset * 
                                           (indicator_rect.height - thumb_height) / 
                                           (total_content_height - visible_height))
            
            thumb_rect = pygame.Rect(indicator_rect.x, thumb_y, indicator_width, thumb_height)
            pygame.draw.rect(surface, (150, 150, 150), thumb_rect)
    
    def draw_footer(self, surface, fonts):
        """Draw the footer section."""
        small_font = fonts.get('small')
        
        if small_font:
            # Last refresh time
            if self.last_refresh_time > 0:
                time_since_refresh = int(time.time() - self.last_refresh_time)
                refresh_text = f"Last updated: {time_since_refresh}s ago"
                refresh_surface = small_font.render(refresh_text, True, (150, 150, 150))
                refresh_rect = refresh_surface.get_rect()
                refresh_rect.x = 20
                refresh_rect.centery = self.footer_rect.centery
                surface.blit(refresh_surface, refresh_rect)
            
            # Instructions
            instructions = "Use mouse wheel to scroll • Double-click to join room • Right-click for options"
            instr_surface = small_font.render(instructions, True, (120, 120, 120))
            instr_rect = instr_surface.get_rect(center=self.footer_rect.center)
            surface.blit(instr_surface, instr_rect)

class CreateRoomDialog:
    """Dialog for creating a new game room."""
    
    def __init__(self, screen_width: int, screen_height: int,
                 create_callback: Callable, cancel_callback: Callable):
        self.screen_width = screen_width
        self.screen_height = screen_height
        self.create_callback = create_callback
        self.cancel_callback = cancel_callback
        
        # Dialog dimensions
        dialog_width = 450
        dialog_height = 350
        dialog_x = (screen_width - dialog_width) // 2
        dialog_y = (screen_height - dialog_height) // 2
        
        self.dialog_rect = pygame.Rect(dialog_x, dialog_y, dialog_width, dialog_height)
        self.overlay_color = (0, 0, 0, 180)
        
        # Input fields
        from .auth_ui import InputField
        
        field_width = 350
        field_height = 40
        field_x = dialog_x + (dialog_width - field_width) // 2
        
        self.room_name_field = InputField(
            field_x, dialog_y + 80, field_width, field_height,
            "Enter room name"
        )
        
        # Settings
        self.is_private = False
        self.max_players = 4
        
        # Buttons
        button_width = 100
        button_height = 40
        button_spacing = 20
        total_button_width = 2 * button_width + button_spacing
        button_start_x = dialog_x + (dialog_width - total_button_width) // 2
        
        self.create_button = Button(
            button_start_x, dialog_y + 250, button_width, button_height,
            "Create", self.attempt_create
        )
        
        self.cancel_button = Button(
            button_start_x + button_width + button_spacing, dialog_y + 250,
            button_width, button_height, "Cancel", self.cancel_callback
        )
        
        # Checkbox for private room
        self.private_checkbox_rect = pygame.Rect(dialog_x + 50, dialog_y + 160, 20, 20)
        
        self.widgets = [self.room_name_field, self.create_button, self.cancel_button]
    
    def attempt_create(self):
        """Attempt to create the room."""
        room_name = self.room_name_field.text.strip()
        
        if not room_name:
            return  # Could show error message
        
        if len(room_name) > 30:
            return  # Could show error message
        
        self.create_callback(room_name, self.is_private, self.max_players)
    
    def handle_event(self, event):
        """Handle pygame events."""
        for widget in self.widgets:
            widget.handle_event(event)
        
        # Handle private checkbox
        if event.type == pygame.MOUSEBUTTONDOWN:
            if self.private_checkbox_rect.collidepoint(event.pos):
                self.is_private = not self.is_private
        
        # Handle Enter key
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_RETURN:
                self.attempt_create()
            elif event.key == pygame.K_ESCAPE:
                self.cancel_callback()
    
    def draw(self, surface, fonts):
        """Draw the create room dialog."""
        # Overlay
        overlay = pygame.Surface((self.screen_width, self.screen_height), pygame.SRCALPHA)
        overlay.fill(self.overlay_color)
        surface.blit(overlay, (0, 0))
        
        # Dialog background
        pygame.draw.rect(surface, (60, 60, 70), self.dialog_rect)
        pygame.draw.rect(surface, (100, 100, 110), self.dialog_rect, 3)
        
        # Title
        large_font = fonts.get('large')
        if large_font:
            title_text = large_font.render("Create Room", True, (255, 255, 255))
            title_rect = title_text.get_rect(center=(self.dialog_rect.centerx, 
                                                   self.dialog_rect.y + 40))
            surface.blit(title_text, title_rect)
        
        # Draw widgets
        medium_font = fonts.get('medium')
        if medium_font:
            for widget in self.widgets:
                widget.draw(surface, medium_font)
        
        # Private room checkbox
        small_font = fonts.get('small')
        if small_font:
            # Checkbox
            checkbox_color = (100, 255, 100) if self.is_private else (200, 200, 200)
            pygame.draw.rect(surface, (255, 255, 255), self.private_checkbox_rect)
            pygame.draw.rect(surface, checkbox_color, self.private_checkbox_rect, 2)
            
            if self.is_private:
                # Checkmark
                pygame.draw.lines(surface, (0, 150, 0), False, [
                    (self.private_checkbox_rect.x + 4, self.private_checkbox_rect.y + 10),
                    (self.private_checkbox_rect.x + 8, self.private_checkbox_rect.y + 14),
                    (self.private_checkbox_rect.x + 16, self.private_checkbox_rect.y + 6)
                ], 3)
            
            # Label
            private_text = small_font.render("Private Room", True, (255, 255, 255))
            private_rect = private_text.get_rect()
            private_rect.x = self.private_checkbox_rect.right + 10
            private_rect.centery = self.private_checkbox_rect.centery
            surface.blit(private_text, private_rect)
        
        # Instructions
        if small_font:
            instructions = [
                "• Enter a name for your room",
                "• Private rooms require invitation",
                "• Press Enter to create, Escape to cancel"
            ]
            
            for i, instruction in enumerate(instructions):
                text_surface = small_font.render(instruction, True, (180, 180, 180))
                text_rect = text_surface.get_rect()
                text_rect.x = self.dialog_rect.x + 30
                text_rect.y = self.dialog_rect.y + 200 + i * 18
                surface.blit(text_surface, text_rect)
