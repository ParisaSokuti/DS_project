#!/usr/bin/env python3
"""
Connection Reliability Test for Hokm WebSocket Card Game Server

This script tests connection stability and reliability:
1. Rapid connect/disconnect cycles
2. Network interruption simulation
3. Reconnection after disconnection
4. Memory leak and cleanup detection
5. Concurrent connection stress testing

Usage: python test_connection_reliability.py
"""

import asyncio
import websockets
import json
import time
import sys
import gc
import psutil
import os
import random
from typing import Dict, List, Optional, Any, Tuple

class ConnectionTest:
    def __init__(self):
        self.server_uri = "ws://localhost:8765"
        self.room_code = "TEST_CONN"
        self.results = []
        self.initial_memory = None
        self.process = None
        
    def add_result(self, test_name: str, success: bool, message: str, details: List[str] = None):
        """Add a test result"""
        result = {
            'test': test_name,
            'success': success,
            'message': message,
            'details': details or [],
            'timestamp': time.time()
        }
        self.results.append(result)
        
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"\n{status} {test_name}: {message}")
        if details:
            for detail in details:
                print(f"  - {detail}")
                
    def get_memory_usage(self) -> int:
        """Get current process memory usage in MB"""
        try:
            if not self.process:
                self.process = psutil.Process(os.getpid())
            return self.process.memory_info().rss // 1024 // 1024  # Convert to MB
        except:
            return 0
            
    async def test_rapid_connections(self) -> None:
        """Test rapid connection/disconnection cycles"""
        print("\n🔄 Testing Rapid Connect/Disconnect Cycles...")
        
        num_cycles = 10
        successful_connects = 0
        successful_disconnects = 0
        connection_times = []
        errors = []
        
        start_memory = self.get_memory_usage()
        
        try:
            for i in range(num_cycles):
                cycle_start = time.time()
                
                try:
                    # Connect
                    websocket = await asyncio.wait_for(
                        websockets.connect(self.server_uri), 
                        timeout=5.0
                    )
                    successful_connects += 1
                    
                    # Send a join message
                    join_msg = {
                        'type': 'join',
                        'room_code': f"{self.room_code}_{i}"
                    }
                    await websocket.send(json.dumps(join_msg))
                    
                    # Try to receive response (optional)
                    try:
                        response = await asyncio.wait_for(websocket.recv(), timeout=2.0)
                        # Parse to ensure it's valid JSON
                        json.loads(response)
                    except asyncio.TimeoutError:
                        pass  # Server might be slow, not critical
                    
                    # Disconnect
                    await websocket.close()
                    successful_disconnects += 1
                    
                    cycle_time = time.time() - cycle_start
                    connection_times.append(cycle_time)
                    
                    print(f"  Cycle {i+1}/{num_cycles}: {cycle_time:.3f}s")
                    
                    # Small delay to prevent overwhelming the server
                    await asyncio.sleep(0.1)
                    
                except Exception as e:
                    errors.append(f"Cycle {i+1}: {str(e)}")
                    print(f"  Cycle {i+1}/{num_cycles}: ERROR - {str(e)}")
                    
        except Exception as e:
            errors.append(f"Overall error: {str(e)}")
            
        end_memory = self.get_memory_usage()
        memory_increase = end_memory - start_memory
        
        # Calculate statistics
        avg_time = sum(connection_times) / len(connection_times) if connection_times else 0
        max_time = max(connection_times) if connection_times else 0
        
        details = [
            f"Successful connections: {successful_connects}/{num_cycles}",
            f"Successful disconnections: {successful_disconnects}/{num_cycles}",
            f"Average cycle time: {avg_time:.3f}s",
            f"Max cycle time: {max_time:.3f}s",
            f"Memory increase: {memory_increase} MB",
            f"Errors: {len(errors)}"
        ]
        
        if errors:
            details.extend([f"Error details:"] + errors[:5])  # Show first 5 errors
            
        # Determine success criteria
        success_rate = successful_connects / num_cycles if num_cycles > 0 else 0
        memory_leak_threshold = 50  # MB
        
        if success_rate >= 0.9 and memory_increase < memory_leak_threshold and len(errors) <= 2:
            self.add_result(
                "Rapid Connections",
                True,
                f"Passed rapid connection test ({success_rate*100:.1f}% success rate)",
                details
            )
        else:
            failure_reasons = []
            if success_rate < 0.9:
                failure_reasons.append(f"Low success rate: {success_rate*100:.1f}%")
            if memory_increase >= memory_leak_threshold:
                failure_reasons.append(f"Potential memory leak: +{memory_increase}MB")
            if len(errors) > 2:
                failure_reasons.append(f"Too many errors: {len(errors)}")
                
            self.add_result(
                "Rapid Connections",
                False,
                f"Failed: {', '.join(failure_reasons)}",
                details
            )
            
    async def test_network_interruption_simulation(self) -> None:
        """Test handling of simulated network interruptions"""
        print("\n📡 Testing Network Interruption Simulation...")
        
        connections_before = 0
        connections_after = 0
        reconnections_successful = 0
        interruption_errors = []
        
        try:
            # Create multiple connections
            clients = []
            for i in range(5):
                try:
                    ws = await websockets.connect(self.server_uri)
                    # Join a room
                    join_msg = {'type': 'join', 'room_code': f"{self.room_code}_NET_{i}"}
                    await ws.send(json.dumps(join_msg))
                    
                    # Wait for join response
                    try:
                        response = await asyncio.wait_for(ws.recv(), timeout=3.0)
                        json.loads(response)  # Validate JSON
                        clients.append(ws)
                        connections_before += 1
                    except:
                        await ws.close()
                        
                except Exception as e:
                    interruption_errors.append(f"Initial connection {i}: {str(e)}")
                    
            print(f"  Created {connections_before} initial connections")
            
            # Simulate network interruption by forcefully closing connections
            print("  Simulating network interruption...")
            for ws in clients:
                try:
                    # Force close without proper WebSocket close handshake
                    if hasattr(ws, 'transport') and ws.transport:
                        ws.transport.close()
                except:
                    pass
                    
            # Wait a bit for server to detect disconnections
            await asyncio.sleep(2.0)
            
            # Attempt to reconnect
            print("  Attempting reconnections...")
            for i in range(len(clients)):
                try:
                    # Try to reconnect
                    new_ws = await asyncio.wait_for(
                        websockets.connect(self.server_uri), 
                        timeout=5.0
                    )
                    
                    # Try to join again
                    join_msg = {'type': 'join', 'room_code': f"{self.room_code}_NET_RECONNECT_{i}"}
                    await new_ws.send(json.dumps(join_msg))
                    
                    # Wait for response
                    response = await asyncio.wait_for(new_ws.recv(), timeout=3.0)
                    json.loads(response)  # Validate JSON
                    
                    await new_ws.close()
                    reconnections_successful += 1
                    connections_after += 1
                    
                except Exception as e:
                    interruption_errors.append(f"Reconnection {i}: {str(e)}")
                    
        except Exception as e:
            interruption_errors.append(f"Overall test error: {str(e)}")
            
        details = [
            f"Initial connections: {connections_before}/5",
            f"Successful reconnections: {reconnections_successful}/5",
            f"Final connections: {connections_after}/5",
            f"Errors: {len(interruption_errors)}"
        ]
        
        if interruption_errors:
            details.extend(["Error details:"] + interruption_errors[:3])
            
        # Success criteria: At least 80% reconnection success
        if reconnections_successful >= 4:
            self.add_result(
                "Network Interruption",
                True,
                f"Handled network interruptions well ({reconnections_successful}/5 reconnected)",
                details
            )
        else:
            self.add_result(
                "Network Interruption",
                False,
                f"Poor reconnection handling ({reconnections_successful}/5 reconnected)",
                details
            )
            
    async def test_reconnection_with_session_data(self) -> None:
        """Test reconnection with session persistence"""
        print("\n🔄 Testing Reconnection with Session Data...")
        
        original_player_id = None
        original_username = None
        reconnection_successful = False
        session_data_preserved = False
        errors = []
        
        try:
            # Step 1: Connect and join a room
            print("  Step 1: Initial connection and join...")
            ws1 = await websockets.connect(self.server_uri)
            
            join_msg = {'type': 'join', 'room_code': self.room_code}
            await ws1.send(json.dumps(join_msg))
            
            # Get join response with session data
            response = await asyncio.wait_for(ws1.recv(), timeout=5.0)
            join_data = json.loads(response)
            
            if join_data.get('type') == 'join_success':
                original_player_id = join_data.get('player_id')
                original_username = join_data.get('username')
                print(f"    Original session: {original_username} ({original_player_id[:8]}...)")
            else:
                errors.append(f"Initial join failed: {join_data}")
                
            # Step 2: Disconnect abruptly
            print("  Step 2: Simulating abrupt disconnection...")
            await ws1.close()
            await asyncio.sleep(1.0)  # Wait for server to process disconnection
            
            # Step 3: Attempt reconnection with session data
            print("  Step 3: Attempting reconnection...")
            if original_player_id:
                ws2 = await websockets.connect(self.server_uri)
                
                reconnect_msg = {
                    'type': 'reconnect',
                    'player_id': original_player_id
                }
                await ws2.send(json.dumps(reconnect_msg))
                
                # Wait for reconnection response
                reconnect_response = await asyncio.wait_for(ws2.recv(), timeout=5.0)
                reconnect_data = json.loads(reconnect_response)
                
                if reconnect_data.get('type') == 'join_success':
                    reconnection_successful = True
                    
                    # Check if session data is preserved
                    if (reconnect_data.get('player_id') == original_player_id and
                        reconnect_data.get('username') == original_username):
                        session_data_preserved = True
                        print(f"    Reconnected as: {reconnect_data.get('username')} (same session)")
                    else:
                        print(f"    Reconnected but session changed: {reconnect_data}")
                else:
                    errors.append(f"Reconnection failed: {reconnect_data}")
                    
                await ws2.close()
            else:
                errors.append("No player_id available for reconnection test")
                
        except Exception as e:
            errors.append(f"Reconnection test error: {str(e)}")
            
        details = [
            f"Original session established: {'Yes' if original_player_id else 'No'}",
            f"Reconnection successful: {'Yes' if reconnection_successful else 'No'}",
            f"Session data preserved: {'Yes' if session_data_preserved else 'No'}",
            f"Errors: {len(errors)}"
        ]
        
        if errors:
            details.extend(["Error details:"] + errors)
            
        if reconnection_successful and session_data_preserved:
            self.add_result(
                "Session Reconnection",
                True,
                "Successfully reconnected with preserved session data",
                details
            )
        elif reconnection_successful:
            self.add_result(
                "Session Reconnection",
                True,
                "Reconnection works but session data not fully preserved",
                details + ["⚠️  Consider improving session persistence"]
            )
        else:
            self.add_result(
                "Session Reconnection",
                False,
                "Reconnection failed or not supported",
                details
            )
            
    async def test_concurrent_connections(self) -> None:
        """Test handling of many concurrent connections"""
        print("\n👥 Testing Concurrent Connections...")
        
        num_connections = 20
        successful_connections = 0
        successful_joins = 0
        concurrent_errors = []
        start_memory = self.get_memory_usage()
        
        try:
            # Create many connections simultaneously
            print(f"  Creating {num_connections} concurrent connections...")
            
            async def create_connection(conn_id: int) -> Tuple[bool, bool, str]:
                """Create a single connection and join a room"""
                try:
                    ws = await asyncio.wait_for(
                        websockets.connect(self.server_uri), 
                        timeout=10.0
                    )
                    
                    # Send join message
                    join_msg = {'type': 'join', 'room_code': f"{self.room_code}_CONC_{conn_id}"}
                    await ws.send(json.dumps(join_msg))
                    
                    # Wait for join response
                    response = await asyncio.wait_for(ws.recv(), timeout=5.0)
                    join_data = json.loads(response)
                    
                    # Check if join was successful
                    join_success = join_data.get('type') == 'join_success'
                    
                    # Hold connection briefly
                    await asyncio.sleep(0.5)
                    
                    # Clean disconnect
                    await ws.close()
                    
                    return True, join_success, ""
                    
                except Exception as e:
                    return False, False, str(e)
                    
            # Run all connections concurrently
            connection_tasks = [
                create_connection(i) for i in range(num_connections)
            ]
            
            results = await asyncio.gather(*connection_tasks, return_exceptions=True)
            
            # Process results
            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    concurrent_errors.append(f"Connection {i}: {str(result)}")
                else:
                    connected, joined, error = result
                    if connected:
                        successful_connections += 1
                    if joined:
                        successful_joins += 1
                    if error:
                        concurrent_errors.append(f"Connection {i}: {error}")
                        
        except Exception as e:
            concurrent_errors.append(f"Concurrent test error: {str(e)}")
            
        end_memory = self.get_memory_usage()
        memory_increase = end_memory - start_memory
        
        # Force garbage collection to check for memory leaks
        gc.collect()
        final_memory = self.get_memory_usage()
        
        details = [
            f"Successful connections: {successful_connections}/{num_connections}",
            f"Successful joins: {successful_joins}/{num_connections}",
            f"Connection success rate: {(successful_connections/num_connections)*100:.1f}%",
            f"Join success rate: {(successful_joins/num_connections)*100:.1f}%",
            f"Memory peak increase: {memory_increase} MB",
            f"Memory after cleanup: {final_memory - start_memory} MB",
            f"Errors: {len(concurrent_errors)}"
        ]
        
        if concurrent_errors:
            details.extend(["Error samples:"] + concurrent_errors[:5])
            
        # Success criteria
        connection_rate = successful_connections / num_connections
        join_rate = successful_joins / num_connections
        
        if (connection_rate >= 0.85 and join_rate >= 0.80 and 
            memory_increase < 100 and len(concurrent_errors) < 5):
            self.add_result(
                "Concurrent Connections",
                True,
                f"Handled concurrent connections well ({connection_rate*100:.1f}% success)",
                details
            )
        else:
            failure_reasons = []
            if connection_rate < 0.85:
                failure_reasons.append(f"Low connection rate: {connection_rate*100:.1f}%")
            if join_rate < 0.80:
                failure_reasons.append(f"Low join rate: {join_rate*100:.1f}%")
            if memory_increase >= 100:
                failure_reasons.append(f"High memory usage: +{memory_increase}MB")
            if len(concurrent_errors) >= 5:
                failure_reasons.append(f"Too many errors: {len(concurrent_errors)}")
                
            self.add_result(
                "Concurrent Connections",
                False,
                f"Failed: {', '.join(failure_reasons)}",
                details
            )
            
    async def test_cleanup_detection(self) -> None:
        """Test for proper resource cleanup after disconnections"""
        print("\n🧹 Testing Resource Cleanup...")
        
        cleanup_errors = []
        start_memory = self.get_memory_usage()
        
        try:
            # Create and destroy many connections to test cleanup
            print("  Creating and destroying connections to test cleanup...")
            
            for batch in range(5):
                batch_connections = []
                
                # Create 10 connections
                for i in range(10):
                    try:
                        ws = await websockets.connect(self.server_uri)
                        join_msg = {'type': 'join', 'room_code': f"{self.room_code}_CLEANUP_{batch}_{i}"}
                        await ws.send(json.dumps(join_msg))
                        
                        # Quick response check
                        try:
                            await asyncio.wait_for(ws.recv(), timeout=1.0)
                        except:
                            pass
                            
                        batch_connections.append(ws)
                    except Exception as e:
                        cleanup_errors.append(f"Batch {batch} connection {i}: {str(e)}")
                        
                # Close all connections in this batch
                for ws in batch_connections:
                    try:
                        await ws.close()
                    except:
                        pass
                        
                # Force garbage collection
                gc.collect()
                await asyncio.sleep(0.5)  # Let server process cleanup
                
                current_memory = self.get_memory_usage()
                print(f"    Batch {batch+1}/5: Memory at {current_memory} MB")
                
        except Exception as e:
            cleanup_errors.append(f"Cleanup test error: {str(e)}")
            
        # Final memory check
        gc.collect()
        await asyncio.sleep(1.0)  # Final cleanup time
        end_memory = self.get_memory_usage()
        total_memory_increase = end_memory - start_memory
        
        details = [
            f"Starting memory: {start_memory} MB",
            f"Ending memory: {end_memory} MB",
            f"Total memory increase: {total_memory_increase} MB",
            f"Cleanup errors: {len(cleanup_errors)}"
        ]
        
        if cleanup_errors:
            details.extend(["Error samples:"] + cleanup_errors[:3])
            
        # Memory leak threshold
        leak_threshold = 30  # MB
        
        if total_memory_increase < leak_threshold and len(cleanup_errors) < 5:
            self.add_result(
                "Resource Cleanup",
                True,
                f"Good resource cleanup (memory increase: {total_memory_increase} MB)",
                details
            )
        else:
            failure_reasons = []
            if total_memory_increase >= leak_threshold:
                failure_reasons.append(f"Potential memory leak: +{total_memory_increase}MB")
            if len(cleanup_errors) >= 5:
                failure_reasons.append(f"Cleanup errors: {len(cleanup_errors)}")
                
            self.add_result(
                "Resource Cleanup",
                False,
                f"Cleanup issues: {', '.join(failure_reasons)}",
                details
            )
            
    async def test_malformed_message_handling(self) -> None:
        """Test server handling of malformed messages during connection stress"""
        print("\n🔧 Testing Malformed Message Handling...")
        
        malformed_tests = [
            ("Invalid JSON", "{ invalid json }"),
            ("Missing type", '{"room_code": "test"}'),
            ("Unknown type", '{"type": "unknown_message"}'),
            ("Empty message", ""),
            ("Non-JSON string", "this is not json"),
            ("Partial JSON", '{"type": "join", "room_code":'),
        ]
        
        responses_received = 0
        error_responses = 0
        connection_survived = 0
        handling_errors = []
        
        try:
            for test_name, malformed_msg in malformed_tests:
                try:
                    print(f"  Testing: {test_name}")
                    
                    ws = await websockets.connect(self.server_uri)
                    
                    # Send malformed message
                    await ws.send(malformed_msg)
                    
                    # Try to receive error response
                    try:
                        response = await asyncio.wait_for(ws.recv(), timeout=3.0)
                        response_data = json.loads(response)
                        responses_received += 1
                        
                        if response_data.get('type') == 'error':
                            error_responses += 1
                            
                    except asyncio.TimeoutError:
                        # Server might not respond to malformed messages
                        pass
                    except json.JSONDecodeError:
                        # Server sent non-JSON response
                        responses_received += 1
                        
                    # Test if connection is still alive by sending valid message
                    try:
                        valid_msg = '{"type": "join", "room_code": "test_malformed"}'
                        await ws.send(valid_msg)
                        
                        valid_response = await asyncio.wait_for(ws.recv(), timeout=2.0)
                        json.loads(valid_response)  # Should be valid JSON
                        connection_survived += 1
                        
                    except Exception as e:
                        handling_errors.append(f"{test_name} - connection broken: {str(e)}")
                        
                    await ws.close()
                    
                except Exception as e:
                    handling_errors.append(f"{test_name}: {str(e)}")
                    
        except Exception as e:
            handling_errors.append(f"Malformed message test error: {str(e)}")
            
        details = [
            f"Tests run: {len(malformed_tests)}",
            f"Responses received: {responses_received}/{len(malformed_tests)}",
            f"Error responses: {error_responses}/{len(malformed_tests)}",
            f"Connections survived: {connection_survived}/{len(malformed_tests)}",
            f"Handling errors: {len(handling_errors)}"
        ]
        
        if handling_errors:
            details.extend(["Error details:"] + handling_errors[:3])
            
        # Success criteria: Most connections should survive malformed messages
        survival_rate = connection_survived / len(malformed_tests)
        
        if survival_rate >= 0.8 and len(handling_errors) <= 2:
            self.add_result(
                "Malformed Message Handling",
                True,
                f"Server handles malformed messages well ({survival_rate*100:.1f}% survival)",
                details
            )
        else:
            self.add_result(
                "Malformed Message Handling",
                False,
                f"Poor malformed message handling ({survival_rate*100:.1f}% survival)",
                details
            )
            
    def print_summary(self):
        """Print comprehensive test summary"""
        print("\n" + "="*70)
        print("🔗 CONNECTION RELIABILITY TEST SUMMARY")
        print("="*70)
        
        total_tests = len(self.results)
        passed_tests = sum(1 for r in self.results if r['success'])
        failed_tests = total_tests - passed_tests
        
        print(f"Total Tests: {total_tests}")
        print(f"✅ Passed: {passed_tests}")
        print(f"❌ Failed: {failed_tests}")
        print(f"Success Rate: {(passed_tests/total_tests)*100:.1f}%")
        
        print("\nDetailed Results:")
        print("-" * 50)
        
        for result in self.results:
            status = "✅ PASS" if result['success'] else "❌ FAIL"
            print(f"{status} {result['test']}: {result['message']}")
            
        # Reliability assessment
        print("\n" + "="*70)
        print("📊 RELIABILITY ASSESSMENT")
        print("="*70)
        
        if failed_tests == 0:
            print("🎉 EXCELLENT: Your server has excellent connection reliability!")
            print("   All connection scenarios handled properly.")
        elif failed_tests <= 2:
            print("✅ GOOD: Your server has good connection reliability.")
            print("   Minor issues detected, but core functionality is solid.")
        elif failed_tests <= 4:
            print("⚠️  MODERATE: Your server has moderate connection reliability.")
            print("   Several issues detected that should be addressed.")
        else:
            print("❌ POOR: Your server has poor connection reliability.")
            print("   Major connection issues detected that need immediate attention.")
            
        print("\nRecommendations:")
        failed_test_names = [r['test'] for r in self.results if not r['success']]
        
        if "Rapid Connections" in failed_test_names:
            print("  🔧 Improve connection/disconnection handling speed")
        if "Network Interruption" in failed_test_names:
            print("  🔧 Add better network interruption recovery")
        if "Session Reconnection" in failed_test_names:
            print("  🔧 Implement or improve session persistence for reconnections")
        if "Concurrent Connections" in failed_test_names:
            print("  🔧 Optimize server for handling multiple simultaneous connections")
        if "Resource Cleanup" in failed_test_names:
            print("  🔧 Fix memory leaks and improve resource cleanup")
        if "Malformed Message Handling" in failed_test_names:
            print("  🔧 Improve error handling for malformed messages")
            
        if failed_tests == 0:
            print("  🎯 Consider load testing with even more concurrent users")
            print("  🎯 Test with real network conditions (latency, packet loss)")
            
        print("="*70)

async def main():
    """Main test execution"""
    print("🔗 Starting Connection Reliability Test for Hokm Game Server")
    print("="*70)
    print("This test will stress-test connection handling, reconnection,")
    print("and resource cleanup. It may take several minutes to complete.")
    print("="*70)
    
    test = ConnectionTest()
    
    try:
        # Initialize memory tracking
        test.initial_memory = test.get_memory_usage()
        print(f"Initial memory usage: {test.initial_memory} MB")
        
        # Run all reliability tests
        await test.test_rapid_connections()
        await test.test_network_interruption_simulation()
        await test.test_reconnection_with_session_data()
        await test.test_concurrent_connections()
        await test.test_cleanup_detection()
        await test.test_malformed_message_handling()
        
    except KeyboardInterrupt:
        print("\n⚠️  Test interrupted by user")
    except Exception as e:
        print(f"\n💥 Fatal error during testing: {e}")
        import traceback
        traceback.print_exc()
        
    # Print final summary
    test.print_summary()
    
    # Exit with appropriate code
    failed_tests = sum(1 for r in test.results if not r['success'])
    return 0 if failed_tests == 0 else 1

if __name__ == "__main__":
    # Check if required modules are available
    try:
        import psutil
    except ImportError:
        print("❌ Required module 'psutil' not found.")
        print("   Install with: pip install psutil")
        sys.exit(1)
        
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
