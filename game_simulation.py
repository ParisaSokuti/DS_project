#!/usr/bin/env python3
"""
Multi-Player Game Test

This script simulates multiple players joining the game to test the full gameplay flow
and reconnection functionality.
"""

import asyncio
import websockets
import json
import sys
import os
import time
from concurrent.futures import ThreadPoolExecutor

# Add backend directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backend'))

try:
    from client_auth_manager import ClientAuthManager
    from game_states import GameState
except ImportError as e:
    print(f"❌ Import error: {e}")
    sys.exit(1)

SERVER_URI = "ws://192.168.1.26:8765"

class GamePlayer:
    def __init__(self, username, password="123456"):
        self.username = username
        self.password = password
        self.player_id = None
        self.session_file = f".test_session_{username}_{int(time.time())}"
        self.auth_manager = ClientAuthManager()
        self.connected = False
        self.is_human = False  # Set to True for human player
        
    async def connect_and_join(self):
        """Connect, authenticate, and join the game"""
        try:
            print(f"🔗 {self.username}: Connecting to server...")
            ws = await websockets.connect(SERVER_URI)
            
            # Authenticate
            authenticated = await self.auth_manager.authenticate_with_server(ws)
            if not authenticated:
                print(f"❌ {self.username}: Authentication failed")
                return None
            
            # Get player info
            player_info = self.auth_manager.get_player_info()
            self.player_id = player_info['player_id']
            
            # Save session
            with open(self.session_file, 'w') as f:
                f.write(self.player_id)
            
            print(f"✅ {self.username}: Authenticated (ID: {self.player_id[:12]}...)")
            
            # Join room
            await ws.send(json.dumps({
                "type": "join",
                "room_code": "9999"
            }))
            
            response = await ws.recv()
            data = json.loads(response)
            
            if data.get('type') == 'join_success':
                print(f"🎮 {self.username}: Joined game successfully")
                self.connected = True
                return ws
            else:
                print(f"❌ {self.username}: Failed to join game: {data}")
                return None
                
        except Exception as e:
            print(f"❌ {self.username}: Connection error: {e}")
            return None
    
    async def play_game(self, ws):
        """Play the game (automated for bots, interactive for humans)"""
        try:
            while True:
                msg = await asyncio.wait_for(ws.recv(), timeout=60.0)
                data = json.loads(msg)
                msg_type = data.get('type')
                
                if self.is_human:
                    print(f"🎮 {self.username}: {msg_type} - {data}")
                
                if msg_type == 'initial_deal':
                    hand = data.get('hand', [])
                    is_hakem = data.get('is_hakem', False)
                    print(f"🎴 {self.username}: Got initial deal, is_hakem: {is_hakem}")
                    
                    if is_hakem:
                        # Auto-select hokm for bots
                        if not self.is_human:
                            await asyncio.sleep(1)  # Brief pause
                            await ws.send(json.dumps({
                                'type': 'hokm_selected',
                                'suit': 'hearts',  # Default choice
                                'room_code': '9999'
                            }))
                            print(f"🎯 {self.username}: Auto-selected hearts as hokm")
                        else:
                            print(f"🎯 {self.username}: You are hakem! Please select hokm.")
                            # Human player would select hokm here
                            
                elif msg_type == 'turn_start':
                    your_turn = data.get('your_turn', False)
                    hand = data.get('hand', [])
                    
                    if your_turn:
                        print(f"🎯 {self.username}: Your turn! Hand: {hand}")
                        
                        if not self.is_human and hand:
                            # Auto-play first card for bots
                            await asyncio.sleep(1)
                            card = hand[0]
                            await ws.send(json.dumps({
                                "type": "play_card",
                                "room_code": "9999",
                                "player_id": self.player_id,
                                "card": card
                            }))
                            print(f"🃏 {self.username}: Auto-played {card}")
                        else:
                            print(f"🃏 {self.username}: Your turn to play!")
                            # Human player would select card here
                            
                elif msg_type == 'card_played':
                    player = data.get('player')
                    card = data.get('card')
                    if player != self.username:
                        print(f"👀 {self.username}: {player} played {card}")
                        
                elif msg_type == 'trick_result':
                    winner = data.get('winner')
                    print(f"🏆 {self.username}: Trick won by {winner}")
                    
                elif msg_type == 'game_over':
                    winner_team = data.get('winner_team')
                    print(f"🎉 {self.username}: Game over! Team {winner_team} wins!")
                    break
                    
                elif msg_type == 'error':
                    error_msg = data.get('message')
                    print(f"❌ {self.username}: Error: {error_msg}")
                    
        except asyncio.TimeoutError:
            print(f"⏰ {self.username}: Timeout waiting for message")
        except Exception as e:
            print(f"❌ {self.username}: Game error: {e}")
        finally:
            try:
                await ws.close()
            except:
                pass
    
    def cleanup(self):
        """Clean up session file"""
        try:
            if os.path.exists(self.session_file):
                os.remove(self.session_file)
        except:
            pass

async def simulate_game():
    """Simulate a 4-player game"""
    print("🎮 Starting Multi-Player Game Simulation")
    print("=" * 50)
    
    # Create players (3 bots + 1 human spot)
    players = [
        GamePlayer("Bot1"),
        GamePlayer("Bot2"), 
        GamePlayer("Bot3"),
        GamePlayer("Human1")  # This could be a human or bot
    ]
    
    # Connect all players
    connections = []
    for player in players:
        ws = await player.connect_and_join()
        if ws:
            connections.append((player, ws))
        else:
            print(f"❌ Failed to connect {player.username}")
            return
        
        await asyncio.sleep(0.5)  # Small delay between connections
    
    print(f"\n🚀 All players connected! Starting game...")
    
    # Play the game
    tasks = []
    for player, ws in connections:
        task = asyncio.create_task(player.play_game(ws))
        tasks.append(task)
    
    try:
        # Wait for all players to finish
        await asyncio.gather(*tasks)
    except KeyboardInterrupt:
        print("\n❌ Game interrupted")
    finally:
        # Cleanup
        for player, ws in connections:
            try:
                await ws.close()
            except:
                pass
            player.cleanup()

if __name__ == "__main__":
    try:
        asyncio.run(simulate_game())
    except KeyboardInterrupt:
        print("\n❌ Simulation interrupted")
    except Exception as e:
        print(f"❌ Simulation failed: {e}")
