"""
Performance benchmarks for PostgreSQL integration.
Tests response times, throughput, and resource utilization.
"""

import pytest
import asyncio
import time
import psutil
import gc
from typing import Dict, List, Any
from statistics import mean, median
from datetime import datetime, timedelta


@pytest.mark.asyncio
@pytest.mark.performance
@pytest.mark.benchmark
class TestPerformanceBenchmarks:
    """Performance tests for critical database operations."""
    
    async def test_player_creation_performance(self, game_integration, test_data_generator, performance_config):
        """Benchmark player creation performance."""
        num_players = performance_config["concurrent_users"]
        max_response_time = performance_config["max_response_time"]
        
        # Generate test data
        player_data_list = test_data_generator["player"](num_players)
        
        # Measure performance
        start_time = time.time()
        response_times = []
        
        async def create_player(player_data):
            op_start = time.time()
            try:
                player, is_new = await game_integration.create_player_if_not_exists(
                    username=player_data["username"],
                    email=player_data["email"],
                    display_name=player_data["display_name"]
                )
                response_time = time.time() - op_start
                response_times.append(response_time)
                return player, response_time
            except Exception as e:
                response_times.append(time.time() - op_start)
                raise e
        
        # Execute concurrent player creations
        tasks = [create_player(data) for data in player_data_list]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        total_time = time.time() - start_time
        
        # Analyze results
        successful_operations = sum(1 for r in results if not isinstance(r, Exception))
        error_count = len(results) - successful_operations
        
        avg_response_time = mean(response_times) if response_times else float('inf')
        median_response_time = median(response_times) if response_times else float('inf')
        max_response_time_actual = max(response_times) if response_times else float('inf')
        
        # Performance assertions
        assert successful_operations >= num_players * 0.95, f"Success rate too low: {successful_operations}/{num_players}"
        assert avg_response_time < max_response_time, f"Average response time too high: {avg_response_time:.3f}s"
        assert error_count / num_players < 0.05, f"Error rate too high: {error_count}/{num_players}"
        
        # Performance metrics
        throughput = successful_operations / total_time
        print(f"\nPlayer Creation Performance:")
        print(f"  Operations: {successful_operations}/{num_players}")
        print(f"  Throughput: {throughput:.2f} ops/sec")
        print(f"  Response times - Avg: {avg_response_time:.3f}s, Median: {median_response_time:.3f}s, Max: {max_response_time_actual:.3f}s")
        print(f"  Error rate: {(error_count/num_players)*100:.1f}%")
    
    async def test_game_state_persistence_performance(self, game_integration, sample_game_session, sample_game_state, performance_config):
        """Benchmark game state persistence performance."""
        num_operations = performance_config["operations_per_second"] * 2  # 2 seconds worth
        max_response_time = performance_config["max_response_time"]
        
        response_times = []
        
        async def update_game_state(operation_id):
            # Modify game state slightly for each operation
            modified_state = sample_game_state.copy()
            modified_state["current_turn"] = operation_id % 4
            modified_state["operation_id"] = operation_id
            
            start_time = time.time()
            try:
                await game_integration.update_game_state(
                    room_id=sample_game_session.room_id,
                    game_state=modified_state
                )
                response_time = time.time() - start_time
                response_times.append(response_time)
                return response_time
            except Exception as e:
                response_times.append(time.time() - start_time)
                raise e
        
        # Execute operations
        start_time = time.time()
        tasks = [update_game_state(i) for i in range(num_operations)]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        total_time = time.time() - start_time
        
        # Analyze performance
        successful_operations = sum(1 for r in results if not isinstance(r, Exception))
        avg_response_time = mean(response_times) if response_times else float('inf')
        throughput = successful_operations / total_time
        
        # Assertions
        assert successful_operations >= num_operations * 0.95
        assert avg_response_time < max_response_time
        assert throughput >= performance_config["operations_per_second"] * 0.8
        
        print(f"\nGame State Persistence Performance:")
        print(f"  Operations: {successful_operations}/{num_operations}")
        print(f"  Throughput: {throughput:.2f} ops/sec")
        print(f"  Avg response time: {avg_response_time:.3f}s")
    
    async def test_concurrent_database_connections(self, db_manager, performance_config):
        """Test database connection pool performance under load."""
        concurrent_connections = performance_config["concurrent_users"]
        operations_per_connection = 5
        
        connection_times = []
        query_times = []
        
        async def database_operations(connection_id):
            connection_start = time.time()
            
            try:
                async with db_manager.get_session() as session:
                    connection_time = time.time() - connection_start
                    connection_times.append(connection_time)
                    
                    # Perform multiple queries per connection
                    for i in range(operations_per_connection):
                        query_start = time.time()
                        result = await session.execute(
                            "SELECT :conn_id as connection_id, :op_id as operation_id",
                            {"conn_id": connection_id, "op_id": i}
                        )
                        row = result.fetchone()
                        query_time = time.time() - query_start
                        query_times.append(query_time)
                        
                        assert row[0] == connection_id
                        assert row[1] == i
                        
                        # Small delay to simulate real work
                        await asyncio.sleep(0.001)
                
                return True
            except Exception as e:
                print(f"Connection {connection_id} failed: {e}")
                return False
        
        # Execute concurrent database operations
        start_time = time.time()
        tasks = [database_operations(i) for i in range(concurrent_connections)]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        total_time = time.time() - start_time
        
        # Analyze results
        successful_connections = sum(1 for r in results if r is True)
        total_operations = successful_connections * operations_per_connection
        
        avg_connection_time = mean(connection_times) if connection_times else float('inf')
        avg_query_time = mean(query_times) if query_times else float('inf')
        throughput = total_operations / total_time
        
        # Assertions
        assert successful_connections >= concurrent_connections * 0.95
        assert avg_connection_time < 0.1  # 100ms max for connection
        assert avg_query_time < 0.05  # 50ms max for simple query
        assert throughput >= concurrent_connections * 2  # At least 2 ops/sec per connection
        
        print(f"\nConnection Pool Performance:")
        print(f"  Concurrent connections: {successful_connections}/{concurrent_connections}")
        print(f"  Total operations: {total_operations}")
        print(f"  Throughput: {throughput:.2f} ops/sec")
        print(f"  Avg connection time: {avg_connection_time:.3f}s")
        print(f"  Avg query time: {avg_query_time:.3f}s")
    
    async def test_bulk_operations_performance(self, game_integration, sample_game_session, sample_players, performance_config):
        """Test bulk operations performance."""
        num_moves = performance_config["concurrent_users"] * 2
        
        # Generate move data
        moves_data = []
        cards = ["AS", "KS", "QS", "JS", "10S", "9S", "8S", "7S"]
        
        for i in range(num_moves):
            moves_data.append({
                "player_id": sample_players[i % len(sample_players)].id,
                "move_type": "play_card",
                "move_data": {
                    "card": cards[i % len(cards)],
                    "suit": "spades",
                    "round": (i // 4) + 1,
                    "trick": (i % 4) + 1
                }
            })
        
        # Test individual operations
        start_time = time.time()
        individual_times = []
        
        for i, move_data in enumerate(moves_data[:num_moves//2]):
            op_start = time.time()
            await game_integration.record_game_move(
                room_id=sample_game_session.room_id,
                **move_data
            )
            individual_times.append(time.time() - op_start)
        
        individual_total_time = time.time() - start_time
        
        # Test batch operations (if available)
        start_time = time.time()
        try:
            await game_integration.record_game_moves_batch(
                room_id=sample_game_session.room_id,
                moves_data=moves_data[num_moves//2:]
            )
            batch_total_time = time.time() - start_time
            batch_available = True
        except AttributeError:
            # Batch operation not implemented
            batch_total_time = individual_total_time
            batch_available = False
        
        # Performance analysis
        individual_throughput = (num_moves//2) / individual_total_time
        avg_individual_time = mean(individual_times)
        
        print(f"\nBulk Operations Performance:")
        print(f"  Individual operations: {num_moves//2} in {individual_total_time:.2f}s")
        print(f"  Individual throughput: {individual_throughput:.2f} ops/sec")
        print(f"  Avg individual time: {avg_individual_time:.3f}s")
        
        if batch_available:
            batch_throughput = (num_moves//2) / batch_total_time
            speedup = individual_total_time / batch_total_time
            print(f"  Batch operations: {num_moves//2} in {batch_total_time:.2f}s")
            print(f"  Batch throughput: {batch_throughput:.2f} ops/sec")
            print(f"  Speedup: {speedup:.2f}x")
            
            # Batch should be significantly faster
            assert speedup > 1.5, f"Batch operations not efficient enough: {speedup:.2f}x"
        
        # Individual operations should meet minimum performance
        assert individual_throughput >= 10, f"Individual throughput too low: {individual_throughput:.2f} ops/sec"
        assert avg_individual_time < 0.1, f"Individual operations too slow: {avg_individual_time:.3f}s"
    
    async def test_query_optimization_performance(self, db_session, sample_players, performance_config):
        """Test query optimization and indexing performance."""
        # Test various query patterns that should be optimized
        
        query_tests = [
            {
                "name": "Player lookup by username",
                "query": "SELECT * FROM players WHERE username = :username",
                "params": {"username": sample_players[0].username}
            },
            {
                "name": "Player lookup by email",
                "query": "SELECT * FROM players WHERE email = :email", 
                "params": {"email": sample_players[0].email}
            },
            {
                "name": "Active players in last hour",
                "query": "SELECT COUNT(*) FROM players WHERE last_active > :threshold",
                "params": {"threshold": datetime.utcnow() - timedelta(hours=1)}
            },
            {
                "name": "Player statistics aggregation",
                "query": """
                    SELECT 
                        COUNT(*) as total_players,
                        AVG(total_games) as avg_games,
                        MAX(total_score) as max_score
                    FROM players 
                    WHERE is_active = true
                """,
                "params": {}
            }
        ]
        
        results = {}
        
        for test in query_tests:
            times = []
            
            # Run each query multiple times
            for _ in range(10):
                start_time = time.time()
                result = await db_session.execute(test["query"], test["params"])
                # Fetch results to ensure query completion
                _ = result.fetchall()
                query_time = time.time() - start_time
                times.append(query_time)
            
            avg_time = mean(times)
            max_time = max(times)
            min_time = min(times)
            
            results[test["name"]] = {
                "avg_time": avg_time,
                "max_time": max_time,
                "min_time": min_time
            }
            
            # Each optimized query should be fast
            assert avg_time < 0.05, f"{test['name']} too slow: {avg_time:.3f}s average"
            assert max_time < 0.1, f"{test['name']} max time too high: {max_time:.3f}s"
        
        print(f"\nQuery Performance Results:")
        for name, metrics in results.items():
            print(f"  {name}:")
            print(f"    Avg: {metrics['avg_time']:.3f}s, Min: {metrics['min_time']:.3f}s, Max: {metrics['max_time']:.3f}s")
    
    async def test_memory_usage_performance(self, game_integration, test_data_generator, performance_config):
        """Test memory usage during operations."""
        process = psutil.Process()
        initial_memory = process.memory_info().rss / 1024 / 1024  # MB
        
        # Perform memory-intensive operations
        num_operations = performance_config["concurrent_users"]
        max_memory_mb = performance_config["memory_limit_mb"]
        
        # Create many players
        player_data_list = test_data_generator["player"](num_operations)
        
        memory_samples = []
        
        for i, player_data in enumerate(player_data_list):
            await game_integration.create_player_if_not_exists(
                username=player_data["username"],
                email=player_data["email"],
                display_name=player_data["display_name"]
            )
            
            # Sample memory every 10 operations
            if i % 10 == 0:
                current_memory = process.memory_info().rss / 1024 / 1024
                memory_samples.append(current_memory)
                
                # Check memory growth
                memory_growth = current_memory - initial_memory
                assert memory_growth < max_memory_mb, f"Memory usage too high: {memory_growth:.1f}MB"
        
        # Force garbage collection
        gc.collect()
        final_memory = process.memory_info().rss / 1024 / 1024
        
        peak_memory = max(memory_samples) if memory_samples else final_memory
        memory_growth = peak_memory - initial_memory
        
        print(f"\nMemory Usage Performance:")
        print(f"  Initial memory: {initial_memory:.1f}MB")
        print(f"  Peak memory: {peak_memory:.1f}MB")
        print(f"  Final memory: {final_memory:.1f}MB")
        print(f"  Memory growth: {memory_growth:.1f}MB")
        print(f"  Operations: {num_operations}")
        print(f"  Memory per operation: {memory_growth/num_operations:.3f}MB")
        
        # Memory growth should be reasonable
        assert memory_growth < max_memory_mb
        assert memory_growth / num_operations < 1.0  # Less than 1MB per operation
    
    async def test_sustained_load_performance(self, game_integration, test_data_generator, performance_config):
        """Test performance under sustained load."""
        duration_seconds = min(performance_config["test_duration"], 60)  # Max 1 minute for tests
        target_ops_per_sec = performance_config["operations_per_second"]
        
        start_time = time.time()
        operation_times = []
        successful_operations = 0
        errors = 0
        
        async def perform_operation():
            nonlocal successful_operations, errors
            
            try:
                # Mix of different operations
                operation_type = successful_operations % 3
                
                if operation_type == 0:
                    # Create player
                    player_data = test_data_generator["player"]()
                    await game_integration.create_player_if_not_exists(
                        username=f"load_test_{successful_operations}_{player_data['username']}",
                        email=player_data["email"],
                        display_name=player_data["display_name"]
                    )
                elif operation_type == 1:
                    # Search players
                    await game_integration.search_players(
                        username_pattern="load_test_",
                        limit=10
                    )
                else:
                    # Get active players
                    await game_integration.get_active_players(minutes_threshold=60)
                
                successful_operations += 1
            except Exception as e:
                errors += 1
                print(f"Operation failed: {e}")
        
        # Run sustained load
        while time.time() - start_time < duration_seconds:
            # Calculate delay to maintain target ops/sec
            elapsed = time.time() - start_time
            expected_operations = elapsed * target_ops_per_sec
            
            if successful_operations + errors < expected_operations:
                # Need to catch up
                batch_size = min(10, int(expected_operations - (successful_operations + errors)) + 1)
                tasks = [perform_operation() for _ in range(batch_size)]
                await asyncio.gather(*tasks, return_exceptions=True)
            else:
                # Maintain pace
                await perform_operation()
                await asyncio.sleep(0.01)  # Small delay
        
        total_time = time.time() - start_time
        actual_ops_per_sec = successful_operations / total_time
        error_rate = errors / (successful_operations + errors) if (successful_operations + errors) > 0 else 0
        
        print(f"\nSustained Load Performance:")
        print(f"  Duration: {total_time:.1f}s")
        print(f"  Successful operations: {successful_operations}")
        print(f"  Errors: {errors}")
        print(f"  Target ops/sec: {target_ops_per_sec}")
        print(f"  Actual ops/sec: {actual_ops_per_sec:.2f}")
        print(f"  Error rate: {error_rate*100:.1f}%")
        
        # Performance assertions
        assert actual_ops_per_sec >= target_ops_per_sec * 0.8, f"Throughput too low: {actual_ops_per_sec:.2f} ops/sec"
        assert error_rate < 0.05, f"Error rate too high: {error_rate*100:.1f}%"
        assert successful_operations > 0, "No successful operations completed"


@pytest.mark.asyncio
@pytest.mark.performance
class TestScalabilityBenchmarks:
    """Test scalability characteristics of the database integration."""
    
    async def test_connection_pool_scaling(self, db_manager):
        """Test how connection pool scales with load."""
        connection_counts = [5, 10, 20, 50]
        results = {}
        
        for conn_count in connection_counts:
            if conn_count > db_manager.pool_size + db_manager.max_overflow:
                continue  # Skip if beyond pool capacity
                
            async def test_connections():
                start_time = time.time()
                
                async def get_connection():
                    async with db_manager.get_session() as session:
                        result = await session.execute("SELECT 1")
                        return result.fetchone()[0]
                
                tasks = [get_connection() for _ in range(conn_count)]
                await asyncio.gather(*tasks)
                
                return time.time() - start_time
            
            duration = await test_connections()
            throughput = conn_count / duration
            
            results[conn_count] = {
                "duration": duration,
                "throughput": throughput
            }
        
        print(f"\nConnection Pool Scaling:")
        for conn_count, metrics in results.items():
            print(f"  {conn_count} connections: {metrics['duration']:.3f}s, {metrics['throughput']:.2f} conn/sec")
        
        # Verify scaling characteristics
        if len(results) > 1:
            # Throughput should generally increase with more connections (up to a point)
            throughputs = list(results.values())
            max_throughput = max(t["throughput"] for t in throughputs)
            min_throughput = min(t["throughput"] for t in throughputs)
            
            # Allow for some variation in throughput
            assert max_throughput / min_throughput < 10, "Throughput variance too high"
    
    async def test_data_volume_scaling(self, game_integration, test_data_generator):
        """Test performance with increasing data volumes."""
        data_sizes = [100, 500, 1000]
        
        for size in data_sizes:
            # Create baseline data
            player_data_list = test_data_generator["player"](size)
            
            # Measure creation time
            start_time = time.time()
            for player_data in player_data_list:
                await game_integration.create_player_if_not_exists(
                    username=f"scale_test_{size}_{player_data['username']}",
                    email=player_data["email"],
                    display_name=player_data["display_name"]
                )
            creation_time = time.time() - start_time
            
            # Measure search time
            start_time = time.time()
            results = await game_integration.search_players(
                username_pattern=f"scale_test_{size}_",
                limit=size
            )
            search_time = time.time() - start_time
            
            creation_throughput = size / creation_time
            search_throughput = len(results) / search_time
            
            print(f"\nData Volume {size}:")
            print(f"  Creation: {creation_time:.2f}s, {creation_throughput:.2f} ops/sec")
            print(f"  Search: {search_time:.3f}s, {search_throughput:.2f} ops/sec, {len(results)} results")
            
            # Performance should not degrade too much with data size
            assert creation_throughput > 5, f"Creation too slow at size {size}: {creation_throughput:.2f} ops/sec"
            assert search_time < 1.0, f"Search too slow at size {size}: {search_time:.3f}s"
