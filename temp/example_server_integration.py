"""
Example integration of SQLAlchemy 2.0 Async with existing Hokm WebSocket server
This demonstrates how to integrate the database layer with your current asyncio/WebSocket code
"""

import asyncio
import json
import logging
from typing import Dict, Any, Optional
import websockets
from websockets.server import WebSocketServerProtocol

# Import the database integration layer
from backend.database import (
    get_session_manager, 
    game_integration,
    configure_logging,
    get_database_config
)

logger = logging.getLogger(__name__)


class HokmGameServer:
    """
    Enhanced Hokm game server with SQLAlchemy 2.0 async integration
    
    This example shows how to integrate the database layer with your existing
    WebSocket server while maintaining high performance and proper error handling.
    """
    
    def __init__(self):
        self.active_connections: Dict[str, WebSocketServerProtocol] = {}
        self.connection_to_player: Dict[str, str] = {}
        self.connection_to_room: Dict[str, str] = {}
        self.session_manager = None
    
    async def initialize(self):
        """
        Initialize the server with database connection
        Call this before starting the WebSocket server
        """
        # Configure logging based on database config
        config = get_database_config()
        configure_logging(config)
        
        # Initialize session manager
        self.session_manager = await get_session_manager()
        
        # Test database connection
        health = await self.session_manager.health_check()
        if health['status'] != 'healthy':
            raise RuntimeError(f"Database health check failed: {health}")
        
        logger.info("Hokm game server initialized with database integration")
    
    async def cleanup(self):
        """
        Clean up server resources
        Call this during server shutdown
        """
        if self.session_manager:
            await self.session_manager.cleanup()
        logger.info("Server cleanup completed")
    
    async def handle_connection(self, websocket: WebSocketServerProtocol, path: str):
        """
        Handle new WebSocket connection with database integration
        """
        connection_id = f"conn_{id(websocket)}_{asyncio.get_event_loop().time()}"
        
        try:
            # Register connection in database
            await game_integration.register_websocket_connection(
                connection_id=connection_id,
                ip_address=websocket.remote_address[0] if websocket.remote_address else None,
                user_agent=websocket.request_headers.get('User-Agent')
            )
            
            # Track connection locally
            self.active_connections[connection_id] = websocket
            
            logger.info(f"New connection registered: {connection_id}")
            
            # Handle messages
            await self.handle_messages(websocket, connection_id)
            
        except Exception as e:
            logger.error(f"Error handling connection {connection_id}: {e}")
        finally:
            # Clean up connection
            await self.disconnect_client(connection_id)
    
    async def handle_messages(self, websocket: WebSocketServerProtocol, connection_id: str):
        """
        Handle incoming WebSocket messages with database operations
        """
        try:
            async for message in websocket:
                try:
                    data = json.loads(message)
                    await self.process_message(websocket, connection_id, data)
                except json.JSONDecodeError:
                    await self.send_error(websocket, "Invalid JSON format")
                except Exception as e:
                    logger.error(f"Error processing message: {e}")
                    await self.send_error(websocket, "Internal server error")
        
        except websockets.exceptions.ConnectionClosed:
            logger.info(f"Connection {connection_id} closed")
        except Exception as e:
            logger.error(f"Error in message handling: {e}")
    
    async def process_message(self, websocket: WebSocketServerProtocol, connection_id: str, data: Dict[str, Any]):
        """
        Process individual messages with database integration
        """
        message_type = data.get('type')
        
        if message_type == 'join_room':
            await self.handle_join_room(websocket, connection_id, data)
        
        elif message_type == 'leave_room':
            await self.handle_leave_room(websocket, connection_id, data)
        
        elif message_type == 'create_room':
            await self.handle_create_room(websocket, connection_id, data)
        
        elif message_type == 'select_trump':
            await self.handle_trump_selection(websocket, connection_id, data)
        
        elif message_type == 'play_card':
            await self.handle_card_play(websocket, connection_id, data)
        
        elif message_type == 'get_game_state':
            await self.handle_get_game_state(websocket, connection_id, data)
        
        elif message_type == 'ping':
            await self.handle_ping(websocket, connection_id)
        
        else:
            await self.send_error(websocket, f"Unknown message type: {message_type}")
    
    async def handle_create_room(self, websocket: WebSocketServerProtocol, connection_id: str, data: Dict[str, Any]):
        """
        Handle room creation with database persistence
        """
        try:
            room_id = data.get('room_id')
            username = data.get('username')
            game_type = data.get('game_type', 'standard')
            
            if not room_id or not username:
                await self.send_error(websocket, "room_id and username are required")
                return
            
            # Create game room in database
            game = await game_integration.create_game_room(
                room_id=room_id,
                creator_username=username,
                game_type=game_type
            )
            
            # Update connection mappings
            self.connection_to_player[connection_id] = username
            self.connection_to_room[connection_id] = room_id
            
            # Send success response
            await self.send_message(websocket, {
                'type': 'room_created',
                'room_id': room_id,
                'game_id': str(game.id),
                'status': game.status,
                'max_players': game.max_players,
                'current_players': game.current_players
            })
            
            logger.info(f"Room {room_id} created by {username}")
            
        except ValueError as e:
            await self.send_error(websocket, str(e))
        except Exception as e:
            logger.error(f"Error creating room: {e}")
            await self.send_error(websocket, "Failed to create room")
    
    async def handle_join_room(self, websocket: WebSocketServerProtocol, connection_id: str, data: Dict[str, Any]):
        """
        Handle player joining a room with database persistence
        """
        try:
            room_id = data.get('room_id')
            username = data.get('username')
            
            if not room_id or not username:
                await self.send_error(websocket, "room_id and username are required")
                return
            
            # Join game room in database
            game, participant = await game_integration.join_game_room(
                room_id=room_id,
                username=username,
                connection_id=connection_id,
                ip_address=websocket.remote_address[0] if websocket.remote_address else None,
                user_agent=websocket.request_headers.get('User-Agent')
            )
            
            # Update connection mappings
            self.connection_to_player[connection_id] = username
            self.connection_to_room[connection_id] = room_id
            
            # Send success response
            await self.send_message(websocket, {
                'type': 'join_success',
                'room_id': room_id,
                'player_id': str(participant.player_id),
                'position': participant.position,
                'team': participant.team,
                'game_status': game.status
            })
            
            # Broadcast to all players in the room
            await self.broadcast_to_room(room_id, {
                'type': 'player_joined',
                'username': username,
                'position': participant.position,
                'team': participant.team,
                'current_players': game.current_players + 1
            }, exclude_connection=connection_id)
            
            # If game is full, start team assignment
            if game.current_players + 1 >= game.max_players:
                await self.handle_game_full(room_id)
            
            logger.info(f"Player {username} joined room {room_id}")
            
        except ValueError as e:
            await self.send_error(websocket, str(e))
        except Exception as e:
            logger.error(f"Error joining room: {e}")
            await self.send_error(websocket, "Failed to join room")
    
    async def handle_leave_room(self, websocket: WebSocketServerProtocol, connection_id: str, data: Dict[str, Any]):
        """
        Handle player leaving a room with database cleanup
        """
        try:
            room_id = data.get('room_id')
            username = data.get('username')
            
            if not room_id or not username:
                await self.send_error(websocket, "room_id and username are required")
                return
            
            # Leave game room in database
            removed = await game_integration.leave_game_room(room_id, username)
            
            if removed:
                # Update connection mappings
                self.connection_to_player.pop(connection_id, None)
                self.connection_to_room.pop(connection_id, None)
                
                # Send success response
                await self.send_message(websocket, {
                    'type': 'leave_success',
                    'room_id': room_id
                })
                
                # Broadcast to remaining players
                await self.broadcast_to_room(room_id, {
                    'type': 'player_left',
                    'username': username
                }, exclude_connection=connection_id)
                
                logger.info(f"Player {username} left room {room_id}")
            else:
                await self.send_error(websocket, "Not in this room")
                
        except Exception as e:
            logger.error(f"Error leaving room: {e}")
            await self.send_error(websocket, "Failed to leave room")
    
    async def handle_game_full(self, room_id: str):
        """
        Handle when a game becomes full - assign teams and select hakem
        """
        try:
            # Assign teams and select hakem
            team_assignments = await game_integration.assign_teams_and_hakem(room_id)
            
            # Broadcast team assignments to all players
            await self.broadcast_to_room(room_id, {
                'type': 'teams_assigned',
                'teams': {
                    'team1': [{'username': p.player.username, 'position': p.position} 
                             for p in team_assignments['team1']],
                    'team2': [{'username': p.player.username, 'position': p.position} 
                             for p in team_assignments['team2']]
                },
                'hakem': {
                    'username': team_assignments['hakem'].player.username,
                    'position': team_assignments['hakem'].position
                }
            })
            
            logger.info(f"Teams assigned for room {room_id}")
            
        except Exception as e:
            logger.error(f"Error assigning teams: {e}")
            await self.broadcast_to_room(room_id, {
                'type': 'error',
                'message': 'Failed to assign teams'
            })
    
    async def handle_trump_selection(self, websocket: WebSocketServerProtocol, connection_id: str, data: Dict[str, Any]):
        """
        Handle trump suit selection with database persistence
        """
        try:
            room_id = data.get('room_id')
            username = data.get('username')
            trump_suit = data.get('trump_suit')
            
            if not all([room_id, username, trump_suit]):
                await self.send_error(websocket, "room_id, username, and trump_suit are required")
                return
            
            # Record trump selection in database
            await game_integration.record_trump_selection(room_id, username, trump_suit)
            
            # Broadcast trump selection to all players
            await self.broadcast_to_room(room_id, {
                'type': 'trump_selected',
                'trump_suit': trump_suit,
                'selected_by': username
            })
            
            logger.info(f"Trump suit {trump_suit} selected by {username} in room {room_id}")
            
        except ValueError as e:
            await self.send_error(websocket, str(e))
        except Exception as e:
            logger.error(f"Error selecting trump: {e}")
            await self.send_error(websocket, "Failed to select trump")
    
    async def handle_card_play(self, websocket: WebSocketServerProtocol, connection_id: str, data: Dict[str, Any]):
        """
        Handle card play with database persistence
        """
        try:
            room_id = data.get('room_id')
            username = data.get('username')
            card = data.get('card')
            round_number = data.get('round_number', 1)
            trick_number = data.get('trick_number', 1)
            
            if not all([room_id, username, card]):
                await self.send_error(websocket, "room_id, username, and card are required")
                return
            
            # Record card play in database
            move = await game_integration.record_card_play(
                room_id, username, card, round_number, trick_number
            )
            
            # Broadcast card play to all players
            await self.broadcast_to_room(room_id, {
                'type': 'card_played',
                'player': username,
                'card': card,
                'round': round_number,
                'trick': trick_number,
                'move_id': str(move.id)
            })
            
            logger.info(f"Card {card} played by {username} in room {room_id}")
            
        except ValueError as e:
            await self.send_error(websocket, str(e))
        except Exception as e:
            logger.error(f"Error playing card: {e}")
            await self.send_error(websocket, "Failed to play card")
    
    async def handle_get_game_state(self, websocket: WebSocketServerProtocol, connection_id: str, data: Dict[str, Any]):
        """
        Handle game state request with database query
        """
        try:
            room_id = data.get('room_id')
            
            if not room_id:
                await self.send_error(websocket, "room_id is required")
                return
            
            # Get game state from database
            game_state = await game_integration.get_game_state(room_id)
            
            if game_state:
                await self.send_message(websocket, {
                    'type': 'game_state',
                    'data': game_state
                })
            else:
                await self.send_error(websocket, "Game not found")
                
        except Exception as e:
            logger.error(f"Error getting game state: {e}")
            await self.send_error(websocket, "Failed to get game state")
    
    async def handle_ping(self, websocket: WebSocketServerProtocol, connection_id: str):
        """
        Handle ping with connection tracking
        """
        try:
            # Update last ping time in database
            if self.session_manager:
                from backend.database.crud import websocket_connection_crud
                async with self.session_manager.get_session() as session:
                    await websocket_connection_crud.update_last_ping(session, connection_id)
            
            # Send pong response
            await self.send_message(websocket, {'type': 'pong'})
            
        except Exception as e:
            logger.error(f"Error handling ping: {e}")
    
    async def disconnect_client(self, connection_id: str):
        """
        Handle client disconnection with database cleanup
        """
        try:
            # Remove from local tracking
            websocket = self.active_connections.pop(connection_id, None)
            username = self.connection_to_player.pop(connection_id, None)
            room_id = self.connection_to_room.pop(connection_id, None)
            
            # Update database
            await game_integration.handle_websocket_disconnect(connection_id, "normal_disconnect")
            
            # Notify room if player was in a game
            if room_id and username:
                await self.broadcast_to_room(room_id, {
                    'type': 'player_disconnected',
                    'username': username
                }, exclude_connection=connection_id)
            
            logger.info(f"Connection {connection_id} disconnected")
            
        except Exception as e:
            logger.error(f"Error disconnecting client: {e}")
    
    async def broadcast_to_room(self, room_id: str, message: Dict[str, Any], exclude_connection: Optional[str] = None):
        """
        Broadcast message to all connections in a room
        """
        # Find all connections for this room
        room_connections = [
            conn_id for conn_id, r_id in self.connection_to_room.items() 
            if r_id == room_id and conn_id != exclude_connection
        ]
        
        # Send message to all connections
        for conn_id in room_connections:
            websocket = self.active_connections.get(conn_id)
            if websocket:
                try:
                    await self.send_message(websocket, message)
                except Exception as e:
                    logger.warning(f"Failed to send message to {conn_id}: {e}")
    
    async def send_message(self, websocket: WebSocketServerProtocol, message: Dict[str, Any]):
        """
        Send message to a WebSocket connection
        """
        try:
            await websocket.send(json.dumps(message))
        except websockets.exceptions.ConnectionClosed:
            logger.debug("Attempted to send message to closed connection")
        except Exception as e:
            logger.error(f"Error sending message: {e}")
    
    async def send_error(self, websocket: WebSocketServerProtocol, error_message: str):
        """
        Send error message to a WebSocket connection
        """
        await self.send_message(websocket, {
            'type': 'error',
            'message': error_message
        })
    
    async def start_background_tasks(self):
        """
        Start background maintenance tasks
        """
        # Clean up stale connections every 5 minutes
        async def cleanup_task():
            while True:
                try:
                    await asyncio.sleep(300)  # 5 minutes
                    cleaned = await game_integration.cleanup_stale_connections()
                    if cleaned > 0:
                        logger.info(f"Cleaned up {cleaned} stale connections")
                except Exception as e:
                    logger.error(f"Error in cleanup task: {e}")
        
        # Start the task
        asyncio.create_task(cleanup_task())
        logger.info("Background tasks started")


async def main():
    """
    Main server entry point
    """
    # Set up logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Create and initialize server
    server = HokmGameServer()
    
    try:
        # Initialize database connections
        await server.initialize()
        
        # Start background tasks
        await server.start_background_tasks()
        
        # Start WebSocket server
        logger.info("Starting Hokm WebSocket server on localhost:8765")
        
        async with websockets.serve(
            server.handle_connection,
            "localhost",
            8765,
            ping_interval=60,       # Send ping every 60 seconds
            ping_timeout=300,       # 5 minutes timeout for ping response
            close_timeout=300,      # 5 minutes timeout for close handshake
            max_size=1024*1024,     # 1MB max message size
            max_queue=100           # Max queued messages
        ):
            # Keep server running
            await asyncio.Future()  # Run forever
            
    except KeyboardInterrupt:
        logger.info("Received interrupt signal")
    except Exception as e:
        logger.error(f"Server error: {e}")
    finally:
        # Clean up
        await server.cleanup()
        logger.info("Server shutdown complete")


if __name__ == "__main__":
    asyncio.run(main())
