# Session Persistence Implementation

## Problem Solved

Previously, when a player typed 'exit' in the game client, their session was lost and they would get a completely new player ID when restarting the client. This meant no persistent identity across game sessions in the same terminal.

## Solution Implemented

### 1. Terminal-Based Session Files

Instead of using process IDs (which change every restart), the client now uses persistent terminal identifiers:

```python
def get_terminal_session_id():
    """Generate a persistent session ID for the current terminal"""
    # Uses TERM_SESSION_ID, WINDOWID, SSH_TTY, or hostname+username
    # Creates consistent session file name per terminal
```

### 2. Two Exit Commands

- **`exit`**: Preserves session for reconnection
- **`clear_session`**: Clears session for fresh start

### 3. Session Management Functions

```python
def preserve_session():
    """Keep the session file for future reconnections"""
    
def clear_session():
    """Clear the current session file"""
```

## How It Works

### Before (Old Behavior)
```
Terminal 1:
1. Run client → Creates .player_session_123456 → Player 1
2. Type 'exit' → Session deleted
3. Run client → Creates .player_session_789012 → Player 2 (NEW!)
```

### After (New Behavior)  
```
Terminal 1:
1. Run client → Creates .player_session_abc123 → Player 1
2. Type 'exit' → Session preserved
3. Run client → Uses .player_session_abc123 → Player 1 (SAME!)

Terminal 2:
1. Run client → Creates .player_session_def456 → Player 2
2. Different terminal = different session = different player
```

## Benefits

✅ **Persistent Identity**: Same terminal = same player across restarts  
✅ **Multiple Terminals**: Different terminals = different players  
✅ **User Control**: Choose to preserve or clear session  
✅ **Reconnection**: Automatic reconnection to previous game state  
✅ **No Conflicts**: Each terminal has isolated session  

## Usage

### Normal Exit (Preserve Session)
```bash
Select a card to play (1-13), 'exit', or 'clear_session': exit
Exiting client...
💾 Session preserved for future reconnections
📁 Session file: .player_session_abc123
Room cleared. Exiting client.
```

### Clear Session Exit  
```bash
Select a card to play (1-13), 'exit', or 'clear_session': clear_session
Clearing session and exiting...
🗑️ Session cleared
Room cleared. Exiting client.
```

### Next Restart
```bash
python -m backend.client
Connecting to server...
📁 Session file: .player_session_abc123
🔍 Found existing session file with player ID: a728a4fb-bb51-4708-bac7-a2925b6ebd9b
🔄 Attempting to reconnect to previous game...
🔄 Successfully reconnected as Player 1
```

## Testing

Run the comprehensive test suite:

```bash
python tests/run_session_tests.py
```

Individual test files:
- `tests/test_session_persistence.py` - Core session functionality
- `tests/test_terminal_isolation.py` - Multi-terminal behavior  
- `tests/test_session_commands.py` - Exit command behavior
- `tests/test_session_integration.py` - End-to-end scenarios

## Demo

See the session persistence in action:

```bash
python demo_session_persistence.py
```

## Technical Details

### Session File Naming
- **Format**: `.player_session_<hash>`
- **Hash Source**: Terminal ID, SSH session, or hostname+username
- **Location**: Current working directory
- **Content**: Player ID for reconnection

### Environment Variables
- `TERM_SESSION_ID` (macOS Terminal)
- `WINDOWID` (X11 terminals) 
- `SSH_TTY` (SSH sessions)
- Fallback: hostname + username

### Server Integration
- Server validates reconnection requests
- Only original player can reconnect to their slot
- New players get new slots even if room has disconnected players
- Proper session validation prevents slot stealing

## Files Modified

### Core Implementation
- `backend/client.py` - Session persistence logic
- `backend/server.py` - Fixed reconnection slot assignment  
- `backend/network.py` - Enhanced reconnection validation

### Tests Added
- `tests/test_session_persistence.py`
- `tests/test_terminal_isolation.py` 
- `tests/test_session_commands.py`
- `tests/test_session_integration.py`
- `tests/run_session_tests.py`

### Demos Added  
- `demo_session_persistence.py`
