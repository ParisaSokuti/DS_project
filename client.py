# client.py
import asyncio
import websockets
import json
import sys

SERVER_URI = "ws://localhost:8765"

class RoomManager:
    def __init__(self, websocket, username):
        self.ws = websocket
        self.username = username

    async def show_room_options(self):
        while True:
            print("\nWould you like to:")
            print("1. Try another room code")
            print("2. Create a new room")
            print("3. Exit")
            choice = input("Enter your choice (1-3): ").strip()
            if choice == '1':
                room_code = input("Enter the 4-character room code: ").strip().upper()
                if len(room_code) != 4:
                    print("Room code must be 4 characters.")
                    continue
                msg = {
                    "type": "join_room",
                    "username": self.username,
                    "room_code": room_code
                }
                await self.ws.send(json.dumps(msg))
                return "join_room", room_code
            elif choice == '2':
                msg = {
                    "type": "create_room",
                    "username": self.username
                }
                await self.ws.send(json.dumps(msg))
                return "create_room", None
            elif choice == '3':
                print("Exiting.")
                return None, None
            else:
                print("Invalid choice. Please try again.")

    async def handle_room_full(self):
        print("\nWould you like to:")
        print("1. Try another room code")
        print("2. Create a new room")
        print("3. Exit")
        choice = input("Enter your choice (1-3): ").strip()
        if choice == '1':
            room_code = input("Enter the 4-character room code: ").strip().upper()
            if len(room_code) != 4:
                print("Room code must be 4 characters.")
                return await self.show_room_options()
            msg = {
                "type": "join_room",
                "username": self.username,
                "room_code": room_code
            }
            await self.ws.send(json.dumps(msg))
            return "join_room", room_code
        elif choice == '2':
            msg = {
                "type": "create_room",
                "username": self.username
            }
            await self.ws.send(json.dumps(msg))
            return "create_room", None
        elif choice == '3':
            print("Exiting.")
            return None, None
        else:
            print("Invalid choice. Please try again.")
            return await self.show_room_options()

    async def get_room_code(self):
        has_room = input("Do you have a room code? (y/n): ").strip().lower()
        if has_room == 'y':
            room_code = input("Enter the 4-character room code: ").strip().upper()
            if len(room_code) != 4:
                print("Room code must be 4 characters.")
                return await self.show_room_options()
            return "join_room", room_code
        else:
            return "create_room", None

async def main():
    print("Welcome to Hokm!")
    username = input("Enter your username: ").strip()
    if not username:
        print("Username cannot be empty.")
        return

    try:
        async with websockets.connect(SERVER_URI) as ws:
            room_manager = RoomManager(ws, username)
            
            while True:
                action, room_code = await room_manager.get_room_code()
                if action is None:
                    return

                # Send join/create message
                msg = {
                    "type": action,
                    "username": username,
                }
                if room_code:
                    msg["room_code"] = room_code
                await ws.send(json.dumps(msg))

                while True:
                    try:
                        msg = await ws.recv()
                        data = json.loads(msg)
                        if data.get('type') == 'room_status':
                            print("\nCurrent players in room [{}]:".format(data['room_id']))
                            for idx, name in enumerate(data['usernames']):
                                marker = " (You)" if name == username else ""
                                print(f"Player {idx+1}: {name}{marker}")
                            print(f"Players in room: {data['total_players']}/4\n")
                            waiting = 4 - data['total_players']
                            if waiting > 0:
                                print(f"Waiting for {waiting} other players to join...")
                        elif data.get('type') == 'game_start':
                            print("Room is full, ready to play!")
                        elif data.get('type') == 'error':
                            print("Error:", data.get('message'))
                            if "Room does not exist" in data.get('message', ''):
                                action, room_code = await room_manager.show_room_options()
                                if action is None:
                                    return
                                if action == "create_room":
                                    msg = {
                                        "type": action,
                                        "username": username
                                    }
                                    await ws.send(json.dumps(msg))
                                break
                        elif data.get('type') == 'room_joined':
                            pass  # Ignore this message
                        elif data.get('type') == 'room_full':
                            print(data.get('message'))
                            action, room_code = await room_manager.handle_room_full()
                            if action is None:
                                return
                            if action == "create_room":
                                msg = {
                                    "type": action,
                                    "username": username
                                }
                                await ws.send(json.dumps(msg))
                            break
                        else:
                            print("Server:", data)
                    except websockets.ConnectionClosed:
                        print("\nServer is not available. Please make sure the server is running.")
                        sys.exit(1)
                    except websockets.exceptions.ConnectionRefused:
                        print("\nCould not connect to server. Please make sure the server is running.")
                        sys.exit(1)
    except KeyboardInterrupt:
        print("\nClient exited.")
    except websockets.exceptions.ConnectionRefused:
        print("\nCould not connect to server. Please make sure the server is running.")
        sys.exit(1)
    except Exception as e:
        print(f"\nAn error occurred: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())
