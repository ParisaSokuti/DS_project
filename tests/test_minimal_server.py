#!/usr/bin/env python3
"""
Simplified test server without Redis to test basic WebSocket functionality
"""
import asyncio
import websockets
import json

connected_clients = {}
room_players = {}

async def handle_client(websocket, path):
    client_id = f"client_{len(connected_clients)}"
    connected_clients[client_id] = websocket
    print(f"[SERVER] {client_id} connected")
    
    try:
        async for message in websocket:
            try:
                data = json.loads(message)
                msg_type = data.get('type')
                print(f"[SERVER] Received {msg_type} from {client_id}")
                
                if msg_type == 'join':
                    room_code = data.get('room_code', '9999')
                    
                    # Add to room
                    if room_code not in room_players:
                        room_players[room_code] = []
                    
                    room_players[room_code].append({
                        'client_id': client_id,
                        'username': f'Player{len(room_players[room_code])+1}',
                        'websocket': websocket
                    })
                    
                    player_count = len(room_players[room_code])
                    username = f'Player{player_count}'
                    
                    # Send join success
                    await websocket.send(json.dumps({
                        'type': 'join_success',
                        'username': username,
                        'room_code': room_code,
                        'player_count': player_count
                    }))
                    
                    print(f"[SERVER] {username} joined room {room_code} ({player_count}/4)")
                    
                    # Start game if 4 players
                    if player_count == 4:
                        print(f"[SERVER] Starting game in room {room_code}")
                        
                        # Send phase change
                        for player in room_players[room_code]:
                            try:
                                await player['websocket'].send(json.dumps({
                                    'type': 'phase_change',
                                    'new_phase': 'team_assignment'
                                }))
                            except:
                                pass
                        
                        # Send team assignment
                        teams = {
                            'team1': [room_players[room_code][0]['username'], room_players[room_code][2]['username']],
                            'team2': [room_players[room_code][1]['username'], room_players[room_code][3]['username']]
                        }
                        hakem = room_players[room_code][0]['username']
                        
                        for player in room_players[room_code]:
                            try:
                                await player['websocket'].send(json.dumps({
                                    'type': 'team_assignment',
                                    'teams': teams,
                                    'hakem': hakem
                                }))
                            except:
                                pass
                        
                        # Send phase change to hokm selection
                        for player in room_players[room_code]:
                            try:
                                await player['websocket'].send(json.dumps({
                                    'type': 'phase_change',
                                    'new_phase': 'waiting_for_hokm'
                                }))
                            except:
                                pass
                        
                        # Send initial hands
                        for i, player in enumerate(room_players[room_code]):
                            hand = ['AS', 'KH', 'QD', 'JC', '10S']  # Dummy hand
                            is_hakem = (player['username'] == hakem)
                            try:
                                await player['websocket'].send(json.dumps({
                                    'type': 'initial_deal',
                                    'hand': hand,
                                    'is_hakem': is_hakem,
                                    'hakem': hakem
                                }))
                            except:
                                pass
                
                elif msg_type == 'hokm_selected':
                    room_code = data.get('room_code', '9999')
                    suit = data.get('suit')
                    print(f"[SERVER] Hokm selected: {suit}")
                    
                    # Broadcast hokm selection
                    if room_code in room_players:
                        for player in room_players[room_code]:
                            try:
                                await player['websocket'].send(json.dumps({
                                    'type': 'hokm_selected',
                                    'suit': suit
                                }))
                            except:
                                pass
                        
                        # Send phase change to final deal
                        for player in room_players[room_code]:
                            try:
                                await player['websocket'].send(json.dumps({
                                    'type': 'phase_change',
                                    'new_phase': 'final_deal'
                                }))
                            except:
                                pass
                        
                        # Send final hands
                        for player in room_players[room_code]:
                            full_hand = ['AS', 'KH', 'QD', 'JC', '10S', '9H', '8D', '7C', '6S', '5H', '4D', '3C', '2S']
                            try:
                                await player['websocket'].send(json.dumps({
                                    'type': 'final_deal',
                                    'hand': full_hand,
                                    'hokm': suit
                                }))
                            except:
                                pass
                        
                        # Send phase change to gameplay
                        for player in room_players[room_code]:
                            try:
                                await player['websocket'].send(json.dumps({
                                    'type': 'phase_change',
                                    'new_phase': 'gameplay'
                                }))
                            except:
                                pass
                        
                        # Send turn start
                        for i, player in enumerate(room_players[room_code]):
                            your_turn = (i == 0)  # First player starts
                            try:
                                await player['websocket'].send(json.dumps({
                                    'type': 'turn_start',
                                    'current_player': room_players[room_code][0]['username'],
                                    'your_turn': your_turn,
                                    'hand': full_hand
                                }))
                            except:
                                pass
                
            except json.JSONDecodeError:
                print(f"[SERVER] Invalid JSON from {client_id}")
            except Exception as e:
                print(f"[SERVER] Error handling message from {client_id}: {e}")
                
    except websockets.exceptions.ConnectionClosed:
        print(f"[SERVER] {client_id} disconnected")
    except Exception as e:
        print(f"[SERVER] Error with {client_id}: {e}")
    finally:
        if client_id in connected_clients:
            del connected_clients[client_id]

async def main():
    print("Starting simplified test server on ws://localhost:8765")
    async with websockets.serve(handle_client, "localhost", 8765):
        await asyncio.Future()  # run forever

if __name__ == "__main__":
    asyncio.run(main())
