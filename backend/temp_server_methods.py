    async def start_next_round_with_delay(self, room_code, delay_seconds):
        """Start next round after a delay"""
        print(f"[LOG] Waiting {delay_seconds} seconds before starting next round in room {room_code}")
        await asyncio.sleep(delay_seconds)
        await self.start_next_round(room_code)

    async def start_next_round(self, room_code):
        """Start the next round with new hakem selection"""
        try:
            if room_code not in self.active_games:
                print(f"[ERROR] Room {room_code} not found for next round")
                return

            game = self.active_games[room_code]
            
            if game.game_phase == "completed":
                print(f"[LOG] Game in room {room_code} is already completed")
                return

            print(f"[LOG] Starting next round in room {room_code}")
            
            # First send notification about new round starting
            round_number = sum(game.round_scores.values()) + 1
            await self.network_manager.broadcast_to_room(
                room_code,
                'new_round_start',
                {
                    'round_number': round_number,
                    'hakem': game.hakem,
                    'team_scores': game.round_scores
                },
                self.redis_manager
            )
            
            # Start new round (resets state and does initial 5-card deal)
            initial_hands = game.start_new_round(self.redis_manager)
            
            if isinstance(initial_hands, dict) and "error" in initial_hands:
                print(f"[ERROR] Failed to start new round: {initial_hands['error']}")
                return
            
            # Send individual initial hands to each player for hokm selection
            await self.broadcast_initial_hands(room_code, initial_hands)
            
            # Update Redis with new state
            game_state = game.to_redis_dict()
            self.redis_manager.save_game_state(room_code, game_state)
            
            print(f"[LOG] Next round started successfully in room {room_code}")
            
        except Exception as e:
            print(f"[ERROR] Failed to start next round in room {room_code}: {str(e)}")
            import traceback
            traceback.print_exc()

    async def broadcast_initial_hands(self, room_code, hands):
        """Broadcast initial hands (5 cards) to players for hokm selection"""
        try:
            game = self.active_games[room_code]
            
            for player_name, hand in hands.items():
                # Find the player info
                room_players = self.redis_manager.get_room_players(room_code)
                player_info = next((p for p in room_players if p['username'] == player_name), None)
                
                if player_info:
                    is_hakem = (player_name == game.hakem)
                    player_id = player_info['player_id']
                    
                    await self.network_manager.send_to_player(
                        player_id,
                        json.dumps({
                            'type': 'initial_deal',
                            'hand': hand,
                            'hakem': game.hakem,
                            'is_hakem': is_hakem,
                            'you': player_name,
                            'phase': 'hokm_selection'
                        }),
                        self.redis_manager
                    )
                    
        except Exception as e:
            print(f"[ERROR] Failed to broadcast initial hands: {str(e)}")
            import traceback
            traceback.print_exc()
