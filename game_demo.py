#!/usr/bin/env python3
"""
Enhanced Hokm Game Demo - Testing multiplayer functionality
Tests authentication, game flow, and reconnection with 4 players.
"""

import asyncio
import websockets
import json
import random
import time
from typing import Dict, List, Optional, Any

class GameDemoClient:
    """Enhanced client for testing Hokm game functionality"""
    
    def __init__(self, username: str, password: str):
        self.username = username
        self.password = password
        self.websocket: Optional[websockets.WebSocketServerProtocol] = None
        self.player_id: Optional[str] = None
        self.room_code: Optional[str] = None
        self.hand: List[Dict] = []
        self.team: Optional[int] = None
        self.is_hakem: bool = False
        self.current_phase: str = "waiting"
        self.connected = False
        
    async def connect(self):
        """Connect to the game server"""
        try:
            print(f"🔗 {self.username}: Connecting to server...")
            self.websocket = await websockets.connect("ws://localhost:8765")
            self.connected = True
            print(f"✅ {self.username}: Connected successfully")
            
            # Start message handler
            asyncio.create_task(self.handle_messages())
            
            # Authenticate
            await self.authenticate()
            
        except Exception as e:
            print(f"❌ {self.username}: Connection failed: {e}")
            self.connected = False
            
    async def disconnect(self):
        """Disconnect from the server"""
        if self.websocket and self.connected:
            print(f"🔌 {self.username}: Disconnecting...")
            await self.websocket.close()
            self.connected = False
            
    async def reconnect(self):
        """Reconnect to the server"""
        if self.connected:
            await self.disconnect()
            
        await asyncio.sleep(1)  # Wait a moment before reconnecting
        await self.connect()
        
        # Rejoin room after reconnection
        if self.room_code:
            await self.join_room(self.room_code)
            
    async def authenticate(self):
        """Authenticate with the server"""
        auth_message = {
            "type": "auth",
            "username": self.username,
            "password": self.password
        }
        
        await self.send_message(auth_message)
        
    async def join_room(self, room_code: str):
        """Join a game room"""
        self.room_code = room_code
        join_message = {
            "type": "join_room",
            "room_code": room_code
        }
        
        await self.send_message(join_message)
        
    async def select_hokm(self, suit: str):
        """Select hokm suit (only for hakem)"""
        if self.is_hakem:
            hokm_message = {
                "type": "select_hokm",
                "suit": suit
            }
            await self.send_message(hokm_message)
            
    async def play_card(self, card: Dict):
        """Play a card"""
        play_message = {
            "type": "play_card",
            "card": card
        }
        await self.send_message(play_message)
        
    async def send_message(self, message: Dict):
        """Send a message to the server"""
        if self.websocket and self.connected:
            try:
                await self.websocket.send(json.dumps(message))
            except Exception as e:
                print(f"❌ {self.username}: Failed to send message: {e}")
                
    async def handle_messages(self):
        """Handle incoming messages"""
        try:
            async for message in self.websocket:
                try:
                    data = json.loads(message)
                    await self.process_message(data)
                except json.JSONDecodeError:
                    print(f"❌ {self.username}: Invalid JSON received")
                except Exception as e:
                    print(f"❌ {self.username}: Error processing message: {e}")
                    
        except websockets.exceptions.ConnectionClosed:
            print(f"🔌 {self.username}: Connection closed")
            self.connected = False
        except Exception as e:
            print(f"❌ {self.username}: Message handler error: {e}")
            
    async def process_message(self, data: Dict):
        """Process incoming message"""
        message_type = data.get("type")
        
        if message_type == "auth_success":
            self.player_id = data.get("player_id")
            print(f"🔐 {self.username}: Authentication successful (ID: {self.player_id[:8]}...)")
            
        elif message_type == "room_joined":
            print(f"🏠 {self.username}: Joined room {data.get('room_code')}")
            
        elif message_type == "team_assignment":
            self.team = data.get("team")
            hakem = data.get("hakem")
            self.is_hakem = (hakem == self.username)
            print(f"👥 {self.username}: Assigned to team {self.team} {'(HAKEM)' if self.is_hakem else ''}")
            
        elif message_type == "phase_change":
            self.current_phase = data.get("phase")
            print(f"🎯 {self.username}: Game phase changed to {self.current_phase}")
            
        elif message_type == "hokm_selected":
            hokm_suit = data.get("suit")
            print(f"♠️ {self.username}: Hokm selected: {hokm_suit}")
            
        elif message_type == "cards_dealt":
            self.hand = data.get("hand", [])
            print(f"🎴 {self.username}: Received {len(self.hand)} cards")
            
        elif message_type == "turn_to_play":
            player = data.get("player")
            if player == self.username:
                print(f"⭐ {self.username}: It's my turn to play!")
                # Auto-play a random card for demo
                if self.hand:
                    card_to_play = random.choice(self.hand)
                    await asyncio.sleep(0.5)  # Brief pause
                    await self.play_card(card_to_play)
                    
        elif message_type == "card_played":
            player = data.get("player")
            card = data.get("card")
            print(f"🎭 {self.username}: {player} played {card['rank']} of {card['suit']}")
            
        elif message_type == "player_disconnected":
            player = data.get("player")
            print(f"🔴 {self.username}: Player {player} disconnected")
            
        elif message_type == "player_reconnected":
            player = data.get("player")
            print(f"🟢 {self.username}: Player {player} reconnected")
            
        elif message_type == "reconnect_success":
            print(f"🔄 {self.username}: Reconnection successful!")
            
        elif message_type == "error":
            error_msg = data.get("message", "Unknown error")
            print(f"❌ {self.username}: Error: {error_msg}")

class GameDemo:
    """Main demo class"""
    
    def __init__(self):
        self.players: Dict[str, GameDemoClient] = {}
        self.room_code = "5555"  # Use a clean room code
        
    async def setup_players(self):
        """Set up all 4 players"""
        player_configs = [
            ("kasra", "123456"),
            ("parisa", "123456"),
            ("arvin", "123456"),
            ("nima", "123456")
        ]
        
        print("🎮 Setting up game demo with 4 players...")
        
        for username, password in player_configs:
            client = GameDemoClient(username, password)
            self.players[username] = client
            
        # Connect all players
        connection_tasks = []
        for client in self.players.values():
            connection_tasks.append(client.connect())
            
        await asyncio.gather(*connection_tasks)
        await asyncio.sleep(1)  # Wait for connections to stabilize
        
    async def start_game(self):
        """Start the game by having all players join the room"""
        print(f"\n🚀 Starting game in room {self.room_code}...")
        
        # Have all players join the room
        join_tasks = []
        for client in self.players.values():
            join_tasks.append(client.join_room(self.room_code))
            
        await asyncio.gather(*join_tasks)
        await asyncio.sleep(2)  # Wait for room to fill and game to start
        
    async def demonstrate_hokm_selection(self):
        """Demonstrate hokm selection"""
        print(f"\n♠️ Demonstrating hokm selection...")
        
        # Find the hakem
        hakem_client = None
        for client in self.players.values():
            if client.is_hakem:
                hakem_client = client
                break
                
        if hakem_client:
            print(f"👑 {hakem_client.username} is the hakem, selecting hokm...")
            await hakem_client.select_hokm("hearts")
            await asyncio.sleep(1)
            
    async def demonstrate_disconnection(self):
        """Demonstrate player disconnection and reconnection"""
        print(f"\n🔌 Demonstrating disconnection and reconnection...")
        
        # Disconnect parisa
        parisa = self.players["parisa"]
        if parisa.connected:
            print(f"🔴 {parisa.username}: Simulating disconnection...")
            await parisa.disconnect()
            await asyncio.sleep(2)
            
            # Reconnect parisa
            print(f"🟢 {parisa.username}: Attempting to reconnect...")
            await parisa.reconnect()
            await asyncio.sleep(1)
            
    async def simulate_gameplay(self):
        """Simulate some gameplay"""
        print(f"\n🎯 Simulating gameplay...")
        
        # Let the game run for a few seconds to see turn-based play
        await asyncio.sleep(5)
        
    async def cleanup(self):
        """Clean up all connections"""
        print(f"\n🧹 Cleaning up connections...")
        
        disconnect_tasks = []
        for client in self.players.values():
            if client.connected:
                disconnect_tasks.append(client.disconnect())
                
        await asyncio.gather(*disconnect_tasks)
        
    async def run_demo(self):
        """Run the complete game demo"""
        try:
            print("=" * 60)
            print("🎮 HOKM GAME MULTIPLAYER DEMO")
            print("=" * 60)
            
            # Setup phase
            await self.setup_players()
            
            # Start game
            await self.start_game()
            
            # Demonstrate hokm selection
            await self.demonstrate_hokm_selection()
            
            # Demonstrate disconnection/reconnection
            await self.demonstrate_disconnection()
            
            # Simulate some gameplay
            await self.simulate_gameplay()
            
            print("\n" + "=" * 60)
            print("✅ DEMO COMPLETED SUCCESSFULLY!")
            print("=" * 60)
            
        except Exception as e:
            print(f"\n❌ Demo failed: {e}")
            
        finally:
            await self.cleanup()

async def main():
    """Main entry point"""
    demo = GameDemo()
    await demo.run_demo()

if __name__ == "__main__":
    asyncio.run(main())
