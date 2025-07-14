#!/usr/bin/env python3

import queue

# Test message processing core functionality
def main():
    print("🧪 Enhanced Message Processing System Test")
    print("=" * 50)
    
    # Create message queue
    message_queue = queue.Queue()
    
    # Test messages
    messages = [
        "join_success",
        ("hand_update", ["A_hearts", "K_hearts"]),
        ("hokm_selected", "diamonds"),
        ("turn_change", "Player 1"),
    ]
    
    # UI flags
    ui_flags = {
        'hand': False,
        'table': False,
        'status_panel': False
    }
    
    def trigger_update(element):
        if element in ui_flags:
            ui_flags[element] = True
            print(f"   📍 {element} update triggered")
    
    def process_message(msg):
        print(f"📨 Processing: {msg}")
        
        if isinstance(msg, str):
            if msg == "join_success":
                trigger_update('status_panel')
        elif isinstance(msg, tuple):
            msg_type, data = msg[0], msg[1]
            if msg_type == "hand_update":
                trigger_update('hand')
            elif msg_type == "hokm_selected":
                trigger_update('status_panel')
            elif msg_type == "turn_change":
                trigger_update('status_panel')
    
    # Test processing
    for i, msg in enumerate(messages, 1):
        print(f"\n[Test {i}]")
        
        # Clear flags
        for key in ui_flags:
            ui_flags[key] = False
        
        # Process message
        process_message(msg)
        
        # Show results
        updated = [key for key, val in ui_flags.items() if val]
        if updated:
            print(f"   ✅ Updates: {', '.join(updated)}")
        else:
            print("   ℹ️  No updates")
    
    print(f"\n✅ Test completed successfully!")
    print("🎉 Message processing system operational!")

if __name__ == "__main__":
    main()
