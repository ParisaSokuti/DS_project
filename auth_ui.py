#!/usr/bin/env python3
"""
Authentication UI Components for Hokm Game
Handles login, registration, and user interface elements.
"""

import pygame
import re
from typing import Optional, Dict, Callable

class InputField:
    """Input field widget for text entry."""
    
    def __init__(self, x: int, y: int, width: int, height: int, 
                 placeholder: str = "", is_password: bool = False):
        self.rect = pygame.Rect(x, y, width, height)
        self.text = ""
        self.placeholder = placeholder
        self.is_password = is_password
        self.active = False
        self.cursor_pos = 0
        self.cursor_visible = True
        self.cursor_timer = 0
        self.max_length = 50
        
        # Colors
        self.bg_color = (255, 255, 255)
        self.bg_color_active = (240, 248, 255)
        self.border_color = (180, 180, 180)
        self.border_color_active = (100, 149, 237)
        self.text_color = (0, 0, 0)
        self.placeholder_color = (150, 150, 150)
        
    def handle_event(self, event):
        """Handle pygame events for the input field."""
        if event.type == pygame.MOUSEBUTTONDOWN:
            self.active = self.rect.collidepoint(event.pos)
            
        elif event.type == pygame.KEYDOWN and self.active:
            if event.key == pygame.K_BACKSPACE:
                if self.cursor_pos > 0:
                    self.text = self.text[:self.cursor_pos-1] + self.text[self.cursor_pos:]
                    self.cursor_pos -= 1
            elif event.key == pygame.K_DELETE:
                if self.cursor_pos < len(self.text):
                    self.text = self.text[:self.cursor_pos] + self.text[self.cursor_pos+1:]
            elif event.key == pygame.K_LEFT:
                self.cursor_pos = max(0, self.cursor_pos - 1)
            elif event.key == pygame.K_RIGHT:
                self.cursor_pos = min(len(self.text), self.cursor_pos + 1)
            elif event.key == pygame.K_HOME:
                self.cursor_pos = 0
            elif event.key == pygame.K_END:
                self.cursor_pos = len(self.text)
            elif event.unicode and len(self.text) < self.max_length:
                # Add character at cursor position
                if event.unicode.isprintable():
                    self.text = self.text[:self.cursor_pos] + event.unicode + self.text[self.cursor_pos:]
                    self.cursor_pos += 1
    
    def update(self, dt):
        """Update cursor blinking."""
        self.cursor_timer += dt
        if self.cursor_timer >= 500:  # 500ms blink rate
            self.cursor_visible = not self.cursor_visible
            self.cursor_timer = 0
    
    def draw(self, surface, font):
        """Draw the input field."""
        # Background
        bg_color = self.bg_color_active if self.active else self.bg_color
        pygame.draw.rect(surface, bg_color, self.rect)
        
        # Border
        border_color = self.border_color_active if self.active else self.border_color
        border_width = 2 if self.active else 1
        pygame.draw.rect(surface, border_color, self.rect, border_width)
        
        # Text content
        display_text = self.text
        if self.is_password and self.text:
            display_text = "•" * len(self.text)
        
        text_surface = None
        if display_text:
            text_surface = font.render(display_text, True, self.text_color)
        elif not self.active and self.placeholder:
            text_surface = font.render(self.placeholder, True, self.placeholder_color)
        
        if text_surface:
            text_rect = text_surface.get_rect()
            text_rect.centery = self.rect.centery
            text_rect.x = self.rect.x + 10
            
            # Clip text to field width
            clip_rect = self.rect.copy()
            clip_rect.x += 10
            clip_rect.width -= 20
            surface.set_clip(clip_rect)
            surface.blit(text_surface, text_rect)
            surface.set_clip(None)
        
        # Cursor
        if self.active and self.cursor_visible and not self.is_password:
            cursor_x = self.rect.x + 10
            if display_text and self.cursor_pos > 0:
                cursor_text = display_text[:self.cursor_pos]
                cursor_width = font.size(cursor_text)[0]
                cursor_x += cursor_width
            
            cursor_rect = pygame.Rect(cursor_x, self.rect.y + 5, 1, self.rect.height - 10)
            pygame.draw.rect(surface, self.text_color, cursor_rect)

class Button:
    """Button widget with hover and click states."""
    
    def __init__(self, x: int, y: int, width: int, height: int, text: str,
                 callback: Optional[Callable] = None):
        self.rect = pygame.Rect(x, y, width, height)
        self.text = text
        self.callback = callback
        self.hovered = False
        self.pressed = False
        
        # Colors
        self.bg_color = (70, 130, 180)
        self.bg_color_hover = (100, 149, 237)
        self.bg_color_pressed = (65, 105, 225)
        self.text_color = (255, 255, 255)
        self.border_color = (25, 25, 112)
    
    def handle_event(self, event):
        """Handle pygame events for the button."""
        if event.type == pygame.MOUSEMOTION:
            self.hovered = self.rect.collidepoint(event.pos)
            
        elif event.type == pygame.MOUSEBUTTONDOWN:
            if self.rect.collidepoint(event.pos):
                self.pressed = True
                
        elif event.type == pygame.MOUSEBUTTONUP:
            if self.pressed and self.rect.collidepoint(event.pos):
                if self.callback:
                    self.callback()
            self.pressed = False
    
    def draw(self, surface, font):
        """Draw the button."""
        # Background
        if self.pressed:
            bg_color = self.bg_color_pressed
        elif self.hovered:
            bg_color = self.bg_color_hover
        else:
            bg_color = self.bg_color
            
        pygame.draw.rect(surface, bg_color, self.rect)
        pygame.draw.rect(surface, self.border_color, self.rect, 2)
        
        # Text
        text_surface = font.render(self.text, True, self.text_color)
        text_rect = text_surface.get_rect(center=self.rect.center)
        surface.blit(text_surface, text_rect)

class AuthScreen:
    """Base class for authentication screens."""
    
    def __init__(self, screen_width: int, screen_height: int):
        self.screen_width = screen_width
        self.screen_height = screen_height
        self.widgets = []
        self.error_message = ""
        self.success_message = ""
        self.message_timer = 0
        
        # Colors
        self.bg_color = (45, 45, 55)
        self.panel_color = (60, 60, 70)
        self.text_color = (255, 255, 255)
        self.error_color = (255, 100, 100)
        self.success_color = (100, 255, 100)
    
    def show_error(self, message: str):
        """Show an error message."""
        self.error_message = message
        self.success_message = ""
        self.message_timer = 3000  # 3 seconds
    
    def show_success(self, message: str):
        """Show a success message."""
        self.success_message = message
        self.error_message = ""
        self.message_timer = 2000  # 2 seconds
    
    def update(self, dt):
        """Update the screen."""
        if self.message_timer > 0:
            self.message_timer -= dt
            if self.message_timer <= 0:
                self.error_message = ""
                self.success_message = ""
        
        for widget in self.widgets:
            if hasattr(widget, 'update'):
                widget.update(dt)
    
    def handle_event(self, event):
        """Handle pygame events."""
        for widget in self.widgets:
            widget.handle_event(event)
    
    def draw_background(self, surface):
        """Draw the screen background."""
        surface.fill(self.bg_color)
        
        # Draw decorative elements
        # Gradient effect
        for y in range(0, self.screen_height, 4):
            alpha = int(20 * (1 - y / self.screen_height))
            color = (self.bg_color[0] + alpha, self.bg_color[1] + alpha, self.bg_color[2] + alpha)
            pygame.draw.line(surface, color, (0, y), (self.screen_width, y), 4)
    
    def draw_messages(self, surface, font):
        """Draw error/success messages."""
        if self.error_message:
            text_surface = font.render(self.error_message, True, self.error_color)
            text_rect = text_surface.get_rect(center=(self.screen_width // 2, 150))
            
            # Background for better readability
            bg_rect = text_rect.inflate(20, 10)
            pygame.draw.rect(surface, (50, 20, 20), bg_rect)
            pygame.draw.rect(surface, self.error_color, bg_rect, 2)
            
            surface.blit(text_surface, text_rect)
            
        elif self.success_message:
            text_surface = font.render(self.success_message, True, self.success_color)
            text_rect = text_surface.get_rect(center=(self.screen_width // 2, 150))
            
            # Background for better readability
            bg_rect = text_rect.inflate(20, 10)
            pygame.draw.rect(surface, (20, 50, 20), bg_rect)
            pygame.draw.rect(surface, self.success_color, bg_rect, 2)
            
            surface.blit(text_surface, text_rect)

class LoginScreen(AuthScreen):
    """Login screen with username and password fields."""
    
    def __init__(self, screen_width: int, screen_height: int, 
                 login_callback: Callable, register_callback: Callable):
        super().__init__(screen_width, screen_height)
        self.login_callback = login_callback
        self.register_callback = register_callback
        
        # Calculate centered positions
        panel_width = 400
        panel_height = 350
        panel_x = (screen_width - panel_width) // 2
        panel_y = (screen_height - panel_height) // 2
        
        self.panel_rect = pygame.Rect(panel_x, panel_y, panel_width, panel_height)
        
        # Input fields
        field_width = 300
        field_height = 40
        field_x = panel_x + (panel_width - field_width) // 2
        
        self.username_field = InputField(
            field_x, panel_y + 80, field_width, field_height, 
            "Enter username"
        )
        
        self.password_field = InputField(
            field_x, panel_y + 140, field_width, field_height,
            "Enter password", is_password=True
        )
        
        # Buttons
        button_width = 120
        button_height = 40
        button_spacing = 20
        total_button_width = 2 * button_width + button_spacing
        button_start_x = panel_x + (panel_width - total_button_width) // 2
        
        self.login_button = Button(
            button_start_x, panel_y + 220, button_width, button_height,
            "Login", self.attempt_login
        )
        
        self.register_button = Button(
            button_start_x + button_width + button_spacing, panel_y + 220,
            button_width, button_height, "Register", self.go_to_register
        )
        
        self.widgets = [self.username_field, self.password_field, 
                       self.login_button, self.register_button]
    
    def attempt_login(self):
        """Attempt to log in with the entered credentials."""
        username = self.username_field.text.strip()
        password = self.password_field.text.strip()
        
        if not username:
            self.show_error("Please enter a username")
            return
            
        if not password:
            self.show_error("Please enter a password")
            return
        
        # Call the login callback
        self.login_callback(username, password)
    
    def go_to_register(self):
        """Switch to registration screen."""
        self.register_callback()
    
    def handle_event(self, event):
        """Handle pygame events."""
        super().handle_event(event)
        
        # Handle Enter key for login
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_RETURN:
                self.attempt_login()
            elif event.key == pygame.K_TAB:
                # Tab between fields
                if self.username_field.active:
                    self.username_field.active = False
                    self.password_field.active = True
                elif self.password_field.active:
                    self.password_field.active = False
                    self.username_field.active = True
    
    def draw(self, surface, fonts):
        """Draw the login screen."""
        self.draw_background(surface)
        
        # Main panel
        pygame.draw.rect(surface, self.panel_color, self.panel_rect)
        pygame.draw.rect(surface, (100, 100, 110), self.panel_rect, 3)
        
        # Title
        title_font = fonts.get('large')
        if title_font:
            title_text = title_font.render("Hokm Game Login", True, self.text_color)
            title_rect = title_text.get_rect(center=(self.panel_rect.centerx, self.panel_rect.y + 40))
            surface.blit(title_text, title_rect)
        
        # Draw widgets
        medium_font = fonts.get('medium')
        if medium_font:
            for widget in self.widgets:
                widget.draw(surface, medium_font)
        
        # Draw messages
        if medium_font:
            self.draw_messages(surface, medium_font)
        
        # Instructions
        small_font = fonts.get('small')
        if small_font:
            instructions = [
                "• Use Tab to switch between fields",
                "• Press Enter to login",
                "• New player? Click Register"
            ]
            
            for i, instruction in enumerate(instructions):
                text_surface = small_font.render(instruction, True, (180, 180, 180))
                text_rect = text_surface.get_rect(center=(self.panel_rect.centerx, 
                                                        self.panel_rect.bottom + 30 + i * 20))
                surface.blit(text_surface, text_rect)

class RegisterScreen(AuthScreen):
    """Registration screen with additional validation."""
    
    def __init__(self, screen_width: int, screen_height: int,
                 register_callback: Callable, login_callback: Callable):
        super().__init__(screen_width, screen_height)
        self.register_callback = register_callback
        self.login_callback = login_callback
        
        # Calculate centered positions
        panel_width = 450
        panel_height = 450
        panel_x = (screen_width - panel_width) // 2
        panel_y = (screen_height - panel_height) // 2
        
        self.panel_rect = pygame.Rect(panel_x, panel_y, panel_width, panel_height)
        
        # Input fields
        field_width = 350
        field_height = 40
        field_x = panel_x + (panel_width - field_width) // 2
        
        self.username_field = InputField(
            field_x, panel_y + 80, field_width, field_height,
            "Choose username (3-20 characters)"
        )
        
        self.email_field = InputField(
            field_x, panel_y + 140, field_width, field_height,
            "Enter email address"
        )
        
        self.password_field = InputField(
            field_x, panel_y + 200, field_width, field_height,
            "Choose password (6+ characters)", is_password=True
        )
        
        self.confirm_password_field = InputField(
            field_x, panel_y + 260, field_width, field_height,
            "Confirm password", is_password=True
        )
        
        # Buttons
        button_width = 120
        button_height = 40
        button_spacing = 20
        total_button_width = 2 * button_width + button_spacing
        button_start_x = panel_x + (panel_width - total_button_width) // 2
        
        self.register_button = Button(
            button_start_x, panel_y + 340, button_width, button_height,
            "Register", self.attempt_register
        )
        
        self.back_button = Button(
            button_start_x + button_width + button_spacing, panel_y + 340,
            button_width, button_height, "Back to Login", self.go_to_login
        )
        
        self.widgets = [self.username_field, self.email_field, self.password_field,
                       self.confirm_password_field, self.register_button, self.back_button]
    
    def validate_input(self) -> bool:
        """Validate registration input."""
        username = self.username_field.text.strip()
        email = self.email_field.text.strip()
        password = self.password_field.text.strip()
        confirm_password = self.confirm_password_field.text.strip()
        
        # Username validation
        if not username:
            return False, "Please enter a username"
        if len(username) < 3:
            return False, "Username must be at least 3 characters"
        if len(username) > 20:
            return False, "Username must be less than 20 characters"
        if not re.match("^[a-zA-Z0-9_]+$", username):
            return False, "Username can only contain letters, numbers, and underscores"
        
        # Email validation
        if not email:
            return False, "Please enter an email address"
        email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        if not re.match(email_pattern, email):
            return False, "Please enter a valid email address"
        
        # Password validation
        if not password:
            return False, "Please enter a password"
        if len(password) < 6:
            return False, "Password must be at least 6 characters"
        
        # Confirm password
        if password != confirm_password:
            return False, "Passwords do not match"
        
        return True, ""
    
    def attempt_register(self):
        """Attempt to register with the entered information."""
        is_valid, error_message = self.validate_input()
        
        if not is_valid:
            self.show_error(error_message)
            return
        
        # Call the register callback
        username = self.username_field.text.strip()
        email = self.email_field.text.strip()
        password = self.password_field.text.strip()
        
        self.register_callback(username, email, password)
    
    def go_to_login(self):
        """Switch to login screen."""
        self.login_callback()
    
    def handle_event(self, event):
        """Handle pygame events."""
        super().handle_event(event)
        
        # Handle Enter key for registration
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_RETURN:
                self.attempt_register()
            elif event.key == pygame.K_TAB:
                # Tab between fields
                fields = [self.username_field, self.email_field, 
                         self.password_field, self.confirm_password_field]
                
                current_active = -1
                for i, field in enumerate(fields):
                    if field.active:
                        current_active = i
                        field.active = False
                        break
                
                # Move to next field
                next_field = (current_active + 1) % len(fields)
                fields[next_field].active = True
    
    def draw(self, surface, fonts):
        """Draw the registration screen."""
        self.draw_background(surface)
        
        # Main panel
        pygame.draw.rect(surface, self.panel_color, self.panel_rect)
        pygame.draw.rect(surface, (100, 100, 110), self.panel_rect, 3)
        
        # Title
        title_font = fonts.get('large')
        if title_font:
            title_text = title_font.render("Create Account", True, self.text_color)
            title_rect = title_text.get_rect(center=(self.panel_rect.centerx, self.panel_rect.y + 40))
            surface.blit(title_text, title_rect)
        
        # Draw widgets
        medium_font = fonts.get('medium')
        if medium_font:
            for widget in self.widgets:
                widget.draw(surface, medium_font)
        
        # Draw messages
        if medium_font:
            self.draw_messages(surface, medium_font)
        
        # Instructions
        small_font = fonts.get('small')
        if small_font:
            instructions = [
                "• Username: 3-20 characters, letters/numbers/underscore only",
                "• Password: minimum 6 characters",
                "• Use Tab to navigate fields, Enter to register"
            ]
            
            for i, instruction in enumerate(instructions):
                text_surface = small_font.render(instruction, True, (180, 180, 180))
                text_rect = text_surface.get_rect(center=(self.screen_width // 2, 
                                                        self.panel_rect.bottom + 30 + i * 20))
                surface.blit(text_surface, text_rect)

def validate_username(username: str) -> bool:
    """Validate username format."""
    if not username:
        return False, "Username cannot be empty"
    if len(username) < 3:
        return False, "Username must be at least 3 characters"
    if len(username) > 20:
        return False, "Username must be less than 20 characters"
    if not re.match("^[a-zA-Z0-9_]+$", username):
        return False, "Username can only contain letters, numbers, and underscores"
    return True, ""

def validate_email(email: str) -> bool:
    """Validate email format."""
    if not email:
        return False, "Email cannot be empty"
    email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    if not re.match(email_pattern, email):
        return False, "Please enter a valid email address"
    return True, ""

def validate_password(password: str) -> bool:
    """Validate password strength."""
    if not password:
        return False, "Password cannot be empty"
    if len(password) < 6:
        return False, "Password must be at least 6 characters"
    if len(password) > 50:
        return False, "Password must be less than 50 characters"
    return True, ""
