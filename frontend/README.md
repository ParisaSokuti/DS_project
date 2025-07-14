# Frontend Directory

This directory contains all user interface and client-side code for the Hokm Game.

## Structure

```
frontend/
├── hokm_gui_client.py          # Main Pygame GUI client
├── pygame_window.py            # Pygame window utilities
├── auth_demo.html              # Web-based authentication demo
├── components/                 # UI Components
│   ├── auth_ui.py             # Authentication screens
│   ├── lobby_ui.py            # Lobby and room browser
│   ├── waiting_room_ui.py     # Waiting room interface
│   └── game_summary_ui.py     # Game summary display
├── resources/                  # Resource Management
│   ├── game_resources.py      # Asset loader and manager
│   └── create_sample_assets.py # Asset generation utility
└── assets/                     # Game Assets
    ├── cards/                 # Card images (52 cards + back)
    ├── fonts/                 # Font files
    ├── sounds/                # Audio files
    └── ui/                    # UI graphics and backgrounds
```

## Main Components

### hokm_gui_client.py
- Main Pygame-based GUI client
- Integrates authentication, lobby, and gameplay
- Handles input, rendering, and game state management

### Components
- **auth_ui.py**: Login and registration screens
- **lobby_ui.py**: Room browser, game lobbies, room creation
- **waiting_room_ui.py**: Pre-game waiting area with chat
- **game_summary_ui.py**: Post-game statistics and results

### Resources
- **game_resources.py**: Centralized asset management
- Loads and caches cards, fonts, sounds, and UI elements
- Provides easy access to game assets

### Assets
- **cards/**: Complete deck of card images (PNG format)
- **ui/**: UI backgrounds, buttons, panels
- **fonts/**: Game fonts (future use)
- **sounds/**: Audio effects (future use)

## Usage

To run the main GUI client:
```bash
python frontend/hokm_gui_client.py
```

To view the web authentication demo:
```bash
# Open frontend/auth_demo.html in a web browser
```

## Dependencies

- pygame: For GUI rendering and input handling
- asyncio/websockets: For server communication
- Standard library modules for networking and utilities
