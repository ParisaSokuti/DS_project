#!/usr/bin/env python3
"""
Enhanced Message Processing Validation Test
Tests all aspects of the enhanced message processing system.
"""

import pygame
import json
import time
import threading
from hokm_gui_client import HokmGameGUI

class MessageProcessingValidator(HokmGameGUI):
    """Test class to validate message processing functionality."""
    
    def __init__(self):
        super().__init__()
        self.test_results = []
        self.test_count = 0
        
    def test_message_type_handling(self):
        """Test different message types and their processing."""
        print("\n🧪 Testing Message Type Handling...")
        
        test_cases = [
            # String messages
            ("join_success", "string"),
            ("game_starting", "string"),
            ("your_turn", "string"),
            ("waiting_for_players", "string"),
            
            # Tuple messages
            (("hand_update", ["A_of_hearts", "K_of_hearts"]), "tuple"),
            (("hokm_selected", "diamonds"), "tuple"),
            (("turn_change", "North Player"), "tuple"),
            (("card_played", ("9_of_hearts", "north")), "tuple"),
            (("trick_complete", "North Player"), "tuple"),
            (("player_joined", "New Player"), "tuple"),
            (("error", "Connection timeout"), "tuple"),
            
            # Complex messages
            (("game_state_update", {
                'round': 1,
                'trick': 2,
                'scores': {'team1': 3, 'team2': 1}
            }), "complex"),
        ]
        
        for i, (message, msg_type) in enumerate(test_cases):
            print(f"   Test {i+1}: {msg_type.upper()} - {str(message)[:50]}...")
            
            # Clear previous state
            self.clear_ui_flags()
            
            # Process message
            self.message_queue.put(message)
            self.process_messages()
            
            # Check if UI was updated
            updated = any(self.ui_update_flags.values())
            self.log_test_result(f"Message Processing - {msg_type}", updated)
    
    def test_ui_update_flags(self):
        """Test UI update flag system."""
        print("\n🧪 Testing UI Update Flags...")
        
        test_messages = [
            ("hand_update", ["A_of_hearts"], ["hand"]),
            ("hokm_selected", "hearts", ["status_panel"]),
            ("turn_change", "You", ["status_panel"]),
            ("card_played", ("9_of_hearts", "north"), ["table", "status_panel"]),
            ("game_state_update", {'scores': {'team1': 2, 'team2': 1}}, ["status_panel"]),
        ]
        
        for i, (msg_type, msg_data, expected_flags) in enumerate(test_messages):
            print(f"   Test {i+1}: {msg_type} -> {expected_flags}")
            
            # Clear flags
            self.clear_ui_flags()
            
            # Process message
            self.message_queue.put((msg_type, msg_data))
            self.process_messages()
            
            # Check expected flags
            flags_set = [flag for flag, value in self.ui_update_flags.items() if value]
            success = all(flag in flags_set for flag in expected_flags)
            self.log_test_result(f"UI Flags - {msg_type}", success)
    
    def test_animation_triggers(self):
        """Test animation trigger system."""
        print("\n🧪 Testing Animation Triggers...")
        
        animation_tests = [
            ("card_played", ("9_of_hearts", "north"), ["card_play"]),
            ("trick_complete", "North Player", ["trick_complete"]),
            ("game_state_update", {'scores': {'team1': 3, 'team2': 1}}, ["score_update"]),
        ]
        
        for i, (msg_type, msg_data, expected_anims) in enumerate(animation_tests):
            print(f"   Test {i+1}: {msg_type} -> {expected_anims}")
            
            # Clear animations
            for anim in self.animations:
                self.animations[anim]['active'] = False
            
            # Process message
            self.message_queue.put((msg_type, msg_data))
            self.process_messages()
            
            # Check animations
            active_anims = [anim for anim, data in self.animations.items() if data['active']]
            success = any(anim in active_anims for anim in expected_anims)
            self.log_test_result(f"Animation - {msg_type}", success)
    
    def test_state_updates(self):
        """Test game state update accuracy."""
        print("\n🧪 Testing State Updates...")
        
        # Test hokm selection
        self.message_queue.put(("hokm_selected", "hearts"))
        self.process_messages()
        success = self.hokm_suit == "hearts"
        self.log_test_result("State Update - Hokm Selection", success)
        
        # Test turn change
        self.message_queue.put(("turn_change", "North Player"))
        self.process_messages()
        success = self.current_turn == "North Player"
        self.log_test_result("State Update - Turn Change", success)
        
        # Test hand update
        new_cards = ["A_of_hearts", "K_of_hearts", "Q_of_hearts"]
        self.message_queue.put(("hand_update", new_cards))
        self.process_messages()
        success = self.player_cards == new_cards
        self.log_test_result("State Update - Hand Update", success)
        
        # Test score update
        new_scores = {'team1': 5, 'team2': 3}
        self.message_queue.put(("game_state_update", {'scores': new_scores}))
        self.process_messages()
        success = self.scores == new_scores
        self.log_test_result("State Update - Score Update", success)
    
    def test_selective_redrawing(self):
        """Test selective redrawing performance."""
        print("\n🧪 Testing Selective Redrawing...")
        
        # Test different update combinations
        test_cases = [
            ("hand_only", {"hand": True}),
            ("table_only", {"table": True}),
            ("status_only", {"status_panel": True}),
            ("multiple", {"hand": True, "table": True, "status_panel": True}),
        ]
        
        for test_name, flags in test_cases:
            # Set specific flags
            self.ui_update_flags = flags.copy()
            
            # Mock drawing (we can't actually draw in test)
            draw_calls = []
            original_draw_hand = self.draw_hand
            original_draw_table = self.draw_table
            original_draw_status = self.draw_status_panel
            
            def mock_draw_hand():
                draw_calls.append("hand")
            def mock_draw_table():
                draw_calls.append("table")
            def mock_draw_status():
                draw_calls.append("status_panel")
            
            self.draw_hand = mock_draw_hand
            self.draw_table = mock_draw_table
            self.draw_status_panel = mock_draw_status
            
            # Simulate draw call
            if self.ui_update_flags.get('hand', False):
                self.draw_hand()
            if self.ui_update_flags.get('table', False):
                self.draw_table()
            if self.ui_update_flags.get('status_panel', False):
                self.draw_status_panel()
            
            # Restore original methods
            self.draw_hand = original_draw_hand
            self.draw_table = original_draw_table
            self.draw_status_panel = original_draw_status
            
            # Check if correct elements were drawn
            expected_calls = [key for key, value in flags.items() if value]
            success = set(draw_calls) == set(expected_calls)
            self.log_test_result(f"Selective Redraw - {test_name}", success)
    
    def test_error_handling(self):
        """Test error message handling."""
        print("\n🧪 Testing Error Handling...")
        
        error_messages = [
            ("error", "Connection timeout"),
            ("error", "Invalid card played"),
            ("error", "Not your turn"),
            ("invalid_message", "Unknown message type"),
        ]
        
        for i, (msg_type, msg_data) in enumerate(error_messages):
            print(f"   Test {i+1}: {msg_type} - {msg_data}")
            
            # Clear flags
            self.clear_ui_flags()
            
            # Process error message
            self.message_queue.put((msg_type, msg_data))
            self.process_messages()
            
            # Error messages should trigger status panel update
            success = self.ui_update_flags.get('status_panel', False)
            self.log_test_result(f"Error Handling - {msg_type}", success)
    
    def test_performance_metrics(self):
        """Test performance of message processing."""
        print("\n🧪 Testing Performance Metrics...")
        
        # Test message processing speed
        start_time = time.time()
        
        # Process 100 messages rapidly
        for i in range(100):
            self.message_queue.put(("turn_change", f"Player {i % 4}"))
        
        # Process all messages
        self.process_messages()
        
        end_time = time.time()
        processing_time = end_time - start_time
        
        # Should process 100 messages in under 0.1 seconds
        success = processing_time < 0.1
        self.log_test_result(f"Performance - 100 messages in {processing_time:.4f}s", success)
        
        # Test UI flag efficiency
        self.clear_ui_flags()
        self.trigger_ui_update('hand')
        self.trigger_ui_update('table')
        
        # Should have exactly 2 flags set
        flags_set = sum(self.ui_update_flags.values())
        success = flags_set == 2
        self.log_test_result(f"UI Flag Efficiency - {flags_set} flags set", success)
    
    def clear_ui_flags(self):
        """Clear all UI update flags."""
        for key in self.ui_update_flags:
            self.ui_update_flags[key] = False
    
    def log_test_result(self, test_name, success):
        """Log test result."""
        self.test_count += 1
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"      {status} - {test_name}")
        self.test_results.append((test_name, success))
    
    def run_all_tests(self):
        """Run all validation tests."""
        print("\n" + "="*70)
        print("🧪 ENHANCED MESSAGE PROCESSING VALIDATION TESTS")
        print("="*70)
        
        # Initialize game to playing state
        self.game_state = "playing"
        self.calculate_positions()
        
        # Run all test suites
        self.test_message_type_handling()
        self.test_ui_update_flags()
        self.test_animation_triggers()
        self.test_state_updates()
        self.test_selective_redrawing()
        self.test_error_handling()
        self.test_performance_metrics()
        
        # Summary
        print("\n" + "="*70)
        print("📊 TEST SUMMARY")
        print("="*70)
        
        passed = sum(1 for _, success in self.test_results if success)
        total = len(self.test_results)
        
        print(f"   Tests Run: {total}")
        print(f"   Passed: {passed}")
        print(f"   Failed: {total - passed}")
        print(f"   Success Rate: {(passed/total)*100:.1f}%")
        
        if passed == total:
            print("\n   🎉 ALL TESTS PASSED! Message processing system is working correctly.")
        else:
            print("\n   ⚠️  Some tests failed. Check implementation details.")
            
            # Show failed tests
            failed_tests = [name for name, success in self.test_results if not success]
            if failed_tests:
                print(f"\n   Failed Tests:")
                for test in failed_tests:
                    print(f"      • {test}")
        
        print("="*70)

def main():
    """Run the validation tests."""
    pygame.init()
    
    validator = MessageProcessingValidator()
    validator.run_all_tests()
    
    pygame.quit()

if __name__ == "__main__":
    main()
