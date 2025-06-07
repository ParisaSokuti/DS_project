# player.py
from dataclasses import dataclass, field
from typing import Optional
import websockets

@dataclass
class Player:
    player_id: str
    wsconnection: websockets.WebSocketServerProtocol
    username: Optional[str] = None
    current_room: Optional[str] = None
    hand: list = field(default_factory=list)
    is_ready: bool = False
