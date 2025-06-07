# player.py
from dataclasses import dataclass
from typing import Optional
import websockets

@dataclass
class Player:
    player_id: str
    wsconnection: websockets.WebSocketServerProtocol
    username: Optional[str] = None
    currentgame: Optional[str] = None
    hand: list = None
    isready: bool = False
