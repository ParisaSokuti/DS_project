#!/usr/bin/env python3
"""
Comprehensive Load Test Runner
Orchestrates all load testing scenarios for PostgreSQL integration
"""

import asyncio
import json
import sys
import time
import logging
import argparse
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any, Optional
import subprocess
import concurrent.futures

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s'
)
logger = logging.getLogger(__name__)

class LoadTestOrchestrator:
    """Orchestrates comprehensive load testing scenarios"""
    
    def __init__(self, config_path: Optional[str] = None):
        self.config = self._load_config(config_path)
        self.results = {}
        self.start_time = None
        self.end_time = None
        
    def _load_config(self, config_path: Optional[str]) -> Dict[str, Any]:
        """Load configuration file"""
        if config_path and Path(config_path).exists():
            with open(config_path, 'r') as f:
                return json.load(f)
        
        # Default configuration
        return {
            "database": {
                "host": "localhost",
                "port": 5432,
                "database": "hokm_game",
                "user": "postgres",
                "password": "password"
            },
            "redis": {
                "host": "localhost",
                "port": 6379
            },
            "test_scenarios": {
                "baseline_performance": {
                    "enabled": True,
                    "concurrent_connections": 20,
                    "duration_minutes": 5,
                    "description": "Baseline performance test without load"
                },
                "normal_load": {
                    "enabled": True,
                    "concurrent_connections": 50,
                    "duration_minutes": 10,
                    "description": "Normal operational load test"
                },
                "peak_load": {
                    "enabled": True,
                    "concurrent_connections": 100,
                    "duration_minutes": 15,
                    "description": "Peak load test simulating high traffic"
                },
                "stress_test": {
                    "enabled": True,
                    "concurrent_connections": 200,
                    "duration_minutes": 20,
                    "description": "Stress test to find breaking points"
                },
                "migration_load": {
                    "enabled": True,
                    "concurrent_users": 50,
                    "duration_minutes": 10,
                    "description": "Load test during migration process"
                },
                "endurance_test": {
                    "enabled": False,
                    "concurrent_connections": 75,
                    "duration_minutes": 60,
                    "description": "Long-running endurance test"
                }
            },
            "reporting": {
                "output_directory": "load_test_results",
                "generate_summary": True,
                "generate_charts": False,
                "include_raw_data": True
            }
        }
    
    async def run_all_tests(self) -> Dict[str, Any]:
        """Run all enabled test scenarios"""
        logger.info("Starting comprehensive load testing suite")
        self.start_time = datetime.now()
        
        # Create output directory
        output_dir = Path(self.config["reporting"]["output_directory"])
        output_dir.mkdir(exist_ok=True)
        
        # Run test scenarios
        for scenario_name, scenario_config in self.config["test_scenarios"].items():
            if not scenario_config.get("enabled", False):
                logger.info(f"Skipping disabled scenario: {scenario_name}")
                continue
            
            logger.info(f"Running scenario: {scenario_name}")
            try:
                result = await self._run_scenario(scenario_name, scenario_config, output_dir)
                self.results[scenario_name] = result
                logger.info(f"Completed scenario: {scenario_name}")
            except Exception as e:
                logger.error(f"Failed scenario {scenario_name}: {e}")
                self.results[scenario_name] = {
                    "status": "failed",
                    "error": str(e),
                    "timestamp": datetime.now()
                }
        
        self.end_time = datetime.now()
        
        # Generate comprehensive report
        comprehensive_report = await self._generate_comprehensive_report(output_dir)
        
        return comprehensive_report
    
    async def _run_scenario(self, scenario_name: str, scenario_config: Dict[str, Any], output_dir: Path) -> Dict[str, Any]:
        """Run a specific test scenario"""
        scenario_start = time.time()
        output_file = output_dir / f"{scenario_name}_report.json"
        
        if scenario_name == "migration_load":
            return await self._run_migration_load_test(scenario_config, output_file)
        else:
            return await self._run_postgresql_load_test(scenario_name, scenario_config, output_file)
    
    async def _run_postgresql_load_test(self, scenario_name: str, scenario_config: Dict[str, Any], output_file: Path) -> Dict[str, Any]:
        """Run PostgreSQL load test scenario"""
        cmd = [
            sys.executable,
            "postgresql_load_test.py",
            "--duration", str(scenario_config["duration_minutes"]),
            "--connections", str(scenario_config["concurrent_connections"]),
            "--output", str(output_file)
        ]
        
        # Add database connection parameters
        db_config = self.config["database"]
        cmd.extend([
            "--db-host", db_config["host"],
            "--db-port", str(db_config["port"]),
            "--db-name", db_config["database"],
            "--db-user", db_config["user"],
            "--db-password", db_config["password"]
        ])
        
        # Run the test
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=Path(__file__).parent
        )
        
        stdout, stderr = await process.communicate()
        
        if process.returncode == 0:
            # Load and return the test results
            if output_file.exists():
                with open(output_file, 'r') as f:
                    return json.load(f)
            else:
                return {"status": "completed", "output": stdout.decode()}
        else:
            return {
                "status": "failed",
                "returncode": process.returncode,
                "stdout": stdout.decode(),
                "stderr": stderr.decode()
            }
    
    async def _run_migration_load_test(self, scenario_config: Dict[str, Any], output_file: Path) -> Dict[str, Any]:
        """Run migration load test scenario"""
        cmd = [
            sys.executable,
            "migration_load_test.py",
            "--duration", str(scenario_config["duration_minutes"]),
            "--concurrent-users", str(scenario_config["concurrent_users"]),
            "--output", str(output_file)
        ]
        
        # Add connection parameters
        db_config = self.config["database"]
        redis_config = self.config["redis"]
        
        cmd.extend([
            "--postgres-host", db_config["host"],
            "--postgres-port", str(db_config["port"]),
            "--postgres-db", db_config["database"],
            "--postgres-user", db_config["user"],
            "--postgres-password", db_config["password"],
            "--redis-host", redis_config["host"],
            "--redis-port", str(redis_config["port"])
        ])
        
        # Run the test
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=Path(__file__).parent
        )
        
        stdout, stderr = await process.communicate()
        
        if process.returncode == 0:
            if output_file.exists():
                with open(output_file, 'r') as f:
                    return json.load(f)
            else:
                return {"status": "completed", "output": stdout.decode()}
        else:
            return {
                "status": "failed",
                "returncode": process.returncode,
                "stdout": stdout.decode(),
                "stderr": stderr.decode()
            }
    
    async def _generate_comprehensive_report(self, output_dir: Path) -> Dict[str, Any]:
        """Generate comprehensive report combining all test results"""
        report = {
            "test_suite_summary": {
                "start_time": self.start_time,
                "end_time": self.end_time,
                "total_duration": (self.end_time - self.start_time).total_seconds(),
                "scenarios_run": len(self.results),
                "scenarios_passed": len([r for r in self.results.values() if r.get("status") != "failed"]),
                "scenarios_failed": len([r for r in self.results.values() if r.get("status") == "failed"])
            },
            "scenario_results": self.results,
            "performance_comparison": self._compare_scenario_performance(),
            "scaling_analysis": self._analyze_scaling_characteristics(),
            "recommendations": self._generate_comprehensive_recommendations(),
            "configuration": self.config
        }
        
        # Save comprehensive report
        report_file = output_dir / "comprehensive_load_test_report.json"
        with open(report_file, 'w') as f:
            json.dump(report, f, indent=2, default=str)
        
        # Generate markdown summary if requested
        if self.config["reporting"]["generate_summary"]:
            await self._generate_markdown_summary(report, output_dir)
        
        logger.info(f"Comprehensive report saved to {report_file}")
        return report
    
    def _compare_scenario_performance(self) -> Dict[str, Any]:
        """Compare performance across different scenarios"""
        comparison = {
            "query_performance": {},
            "connection_utilization": {},
            "error_rates": {},
            "throughput": {}
        }
        
        for scenario_name, result in self.results.items():
            if result.get("status") == "failed":
                continue
            
            # Extract performance metrics based on scenario type
            if scenario_name == "migration_load":
                if "performance_impact" in result:
                    comparison["query_performance"][scenario_name] = {
                        "avg_read_latency": result["performance_impact"].get("avg_read_latency_during_migration", 0),
                        "avg_write_latency": result["performance_impact"].get("avg_write_latency_during_migration", 0)
                    }
            else:
                # PostgreSQL load test results
                if "load_metrics" in result:
                    load_metrics = result["load_metrics"]
                    comparison["query_performance"][scenario_name] = {
                        "avg_query_time": load_metrics.get("average_query_time", 0),
                        "p95_query_time": load_metrics.get("p95_query_time", 0),
                        "p99_query_time": load_metrics.get("p99_query_time", 0)
                    }
                    
                    comparison["error_rates"][scenario_name] = {
                        "query_failure_rate": load_metrics.get("queries_failed", 0) / max(load_metrics.get("queries_executed", 1), 1),
                        "transaction_failure_rate": load_metrics.get("transactions_failed", 0) / max(load_metrics.get("transactions_completed", 1), 1)
                    }
                    
                    comparison["throughput"][scenario_name] = {
                        "queries_per_second": load_metrics.get("queries_executed", 0) / (self.config["test_scenarios"][scenario_name]["duration_minutes"] * 60),
                        "transactions_per_second": load_metrics.get("transactions_completed", 0) / (self.config["test_scenarios"][scenario_name]["duration_minutes"] * 60)
                    }
                
                if "database_metrics" in result and "connection_stats" in result["database_metrics"]:
                    conn_stats = result["database_metrics"]["connection_stats"]
                    comparison["connection_utilization"][scenario_name] = {
                        "avg_active_connections": conn_stats.get("avg_active_connections", 0),
                        "max_active_connections": conn_stats.get("max_active_connections", 0),
                        "connection_timeouts": conn_stats.get("connection_timeouts", 0)
                    }
        
        return comparison
    
    def _analyze_scaling_characteristics(self) -> Dict[str, Any]:
        """Analyze how the system scales with increasing load"""
        scaling_analysis = {
            "connection_scaling": [],
            "performance_degradation": [],
            "throughput_scaling": [],
            "recommendations": []
        }
        
        # Analyze scaling based on concurrent connections
        scenarios_by_load = sorted(
            [(name, config, self.results.get(name, {})) 
             for name, config in self.config["test_scenarios"].items() 
             if config.get("enabled") and name != "migration_load"],
            key=lambda x: x[1].get("concurrent_connections", 0)
        )
        
        for i, (scenario_name, scenario_config, result) in enumerate(scenarios_by_load):
            if result.get("status") == "failed":
                continue
            
            connections = scenario_config.get("concurrent_connections", 0)
            
            # Extract performance metrics
            avg_query_time = 0
            queries_per_second = 0
            error_rate = 0
            
            if "load_metrics" in result:
                load_metrics = result["load_metrics"]
                avg_query_time = load_metrics.get("average_query_time", 0)
                duration = scenario_config.get("duration_minutes", 1) * 60
                queries_per_second = load_metrics.get("queries_executed", 0) / duration
                error_rate = load_metrics.get("queries_failed", 0) / max(load_metrics.get("queries_executed", 1), 1)
            
            scaling_point = {
                "scenario": scenario_name,
                "concurrent_connections": connections,
                "avg_query_time_ms": avg_query_time,
                "queries_per_second": queries_per_second,
                "error_rate": error_rate
            }
            
            scaling_analysis["connection_scaling"].append(scaling_point)
            
            # Analyze performance degradation
            if i > 0:
                prev_point = scaling_analysis["connection_scaling"][i-1]
                perf_degradation = {
                    "from_scenario": prev_point["scenario"],
                    "to_scenario": scenario_name,
                    "connection_increase": connections - prev_point["concurrent_connections"],
                    "latency_increase_percent": ((avg_query_time - prev_point["avg_query_time_ms"]) / max(prev_point["avg_query_time_ms"], 1)) * 100,
                    "throughput_change_percent": ((queries_per_second - prev_point["queries_per_second"]) / max(prev_point["queries_per_second"], 1)) * 100,
                    "error_rate_change": error_rate - prev_point["error_rate"]
                }
                scaling_analysis["performance_degradation"].append(perf_degradation)
        
        # Generate scaling recommendations
        if scaling_analysis["performance_degradation"]:
            for degradation in scaling_analysis["performance_degradation"]:
                if degradation["latency_increase_percent"] > 50:
                    scaling_analysis["recommendations"].append({
                        "type": "Performance",
                        "priority": "High",
                        "message": f"Significant latency increase ({degradation['latency_increase_percent']:.1f}%) from {degradation['from_scenario']} to {degradation['to_scenario']}"
                    })
                
                if degradation["error_rate_change"] > 0.01:  # 1% increase in error rate
                    scaling_analysis["recommendations"].append({
                        "type": "Reliability",
                        "priority": "Critical",
                        "message": f"Error rate increased by {degradation['error_rate_change']:.2%} from {degradation['from_scenario']} to {degradation['to_scenario']}"
                    })
        
        return scaling_analysis
    
    def _generate_comprehensive_recommendations(self) -> List[Dict[str, str]]:
        """Generate comprehensive recommendations based on all test results"""
        recommendations = []
        
        # Analyze failed scenarios
        failed_scenarios = [name for name, result in self.results.items() if result.get("status") == "failed"]
        if failed_scenarios:
            recommendations.append({
                "category": "Test Execution",
                "priority": "Critical",
                "recommendation": f"Address test failures in scenarios: {', '.join(failed_scenarios)}",
                "rationale": "Failed tests indicate potential system issues or test environment problems"
            })
        
        # Analyze migration performance
        if "migration_load" in self.results and self.results["migration_load"].get("status") != "failed":
            migration_result = self.results["migration_load"]
            
            if "user_experience_impact" in migration_result:
                failure_rate = migration_result["user_experience_impact"].get("failure_rate", 0)
                if failure_rate > 0.01:  # More than 1% failure rate
                    recommendations.append({
                        "category": "Migration",
                        "priority": "High",
                        "recommendation": "Implement better load balancing and circuit breakers during migration",
                        "rationale": f"Migration caused {failure_rate:.2%} request failure rate"
                    })
            
            if "data_consistency" in migration_result:
                consistency_rate = migration_result["data_consistency"].get("consistency_rate", 1.0)
                if consistency_rate < 0.99:
                    recommendations.append({
                        "category": "Data Integrity",
                        "priority": "Critical",
                        "recommendation": "Improve data synchronization mechanisms",
                        "rationale": f"Data consistency rate during migration: {consistency_rate:.2%}"
                    })
        
        # Analyze scaling patterns
        scaling = self._analyze_scaling_characteristics()
        if scaling["recommendations"]:
            recommendations.extend([
                {
                    "category": "Scaling",
                    "priority": rec["priority"],
                    "recommendation": rec["message"],
                    "rationale": "Load testing revealed scaling bottlenecks"
                }
                for rec in scaling["recommendations"][:3]  # Top 3 scaling recommendations
            ])
        
        # Performance recommendations
        performance_comparison = self._compare_scenario_performance()
        if "query_performance" in performance_comparison:
            high_latency_scenarios = [
                name for name, metrics in performance_comparison["query_performance"].items()
                if metrics.get("avg_query_time", 0) > 100  # More than 100ms
            ]
            
            if high_latency_scenarios:
                recommendations.append({
                    "category": "Performance",
                    "priority": "Medium",
                    "recommendation": f"Optimize query performance for scenarios: {', '.join(high_latency_scenarios)}",
                    "rationale": "High query latency detected under load"
                })
        
        return recommendations
    
    async def _generate_markdown_summary(self, report: Dict[str, Any], output_dir: Path):
        """Generate markdown summary report"""
        md_content = f"""# Comprehensive Load Test Results

## Test Suite Summary

- **Start Time:** {report["test_suite_summary"]["start_time"]}
- **End Time:** {report["test_suite_summary"]["end_time"]}
- **Total Duration:** {report["test_suite_summary"]["total_duration"]:.1f} seconds
- **Scenarios Run:** {report["test_suite_summary"]["scenarios_run"]}
- **Scenarios Passed:** {report["test_suite_summary"]["scenarios_passed"]}
- **Scenarios Failed:** {report["test_suite_summary"]["scenarios_failed"]}

## Scenario Results

"""
        
        for scenario_name, result in report["scenario_results"].items():
            status = result.get("status", "unknown")
            md_content += f"### {scenario_name.replace('_', ' ').title()}\n\n"
            md_content += f"**Status:** {status}\n\n"
            
            if status != "failed":
                # Add scenario-specific metrics
                if scenario_name == "migration_load":
                    if "migration_summary" in result:
                        summary = result["migration_summary"]
                        md_content += f"- **Migration Duration:** {summary.get('total_duration', 0):.1f} seconds\n"
                        md_content += f"- **Records Migrated:** {summary.get('records_migrated', 0)}\n"
                        md_content += f"- **Migration Errors:** {summary.get('migration_errors', 0)}\n"
                    
                    if "user_experience_impact" in result:
                        ux_impact = result["user_experience_impact"]
                        md_content += f"- **Request Failures:** {ux_impact.get('request_failures', 0)}\n"
                        md_content += f"- **Request Timeouts:** {ux_impact.get('request_timeouts', 0)}\n"
                else:
                    if "load_metrics" in result:
                        load_metrics = result["load_metrics"]
                        md_content += f"- **Queries Executed:** {load_metrics.get('queries_executed', 0)}\n"
                        md_content += f"- **Queries Failed:** {load_metrics.get('queries_failed', 0)}\n"
                        md_content += f"- **Average Query Time:** {load_metrics.get('average_query_time', 0):.2f}ms\n"
            else:
                md_content += f"**Error:** {result.get('error', 'Unknown error')}\n"
            
            md_content += "\n"
        
        # Add performance comparison
        if "performance_comparison" in report:
            md_content += "## Performance Comparison\n\n"
            
            perf_comp = report["performance_comparison"]
            if "query_performance" in perf_comp:
                md_content += "### Query Performance\n\n"
                md_content += "| Scenario | Avg Query Time (ms) | P95 Query Time (ms) | P99 Query Time (ms) |\n"
                md_content += "|----------|-------------------|-------------------|-------------------|\n"
                
                for scenario, metrics in perf_comp["query_performance"].items():
                    avg_time = metrics.get("avg_query_time", metrics.get("avg_read_latency", 0))
                    p95_time = metrics.get("p95_query_time", 0)
                    p99_time = metrics.get("p99_query_time", 0)
                    md_content += f"| {scenario} | {avg_time:.2f} | {p95_time:.2f} | {p99_time:.2f} |\n"
                
                md_content += "\n"
        
        # Add recommendations
        if "recommendations" in report and report["recommendations"]:
            md_content += "## Recommendations\n\n"
            
            for rec in report["recommendations"]:
                priority = rec.get("priority", "Medium")
                category = rec.get("category", "General")
                recommendation = rec.get("recommendation", "")
                rationale = rec.get("rationale", "")
                
                md_content += f"### {category} - {priority} Priority\n\n"
                md_content += f"**Recommendation:** {recommendation}\n\n"
                md_content += f"**Rationale:** {rationale}\n\n"
        
        # Save markdown report
        md_file = output_dir / "load_test_summary.md"
        with open(md_file, 'w') as f:
            f.write(md_content)
        
        logger.info(f"Markdown summary saved to {md_file}")

def create_sample_config() -> Dict[str, Any]:
    """Create a sample configuration file"""
    config = {
        "database": {
            "host": "localhost",
            "port": 5432,
            "database": "hokm_game",
            "user": "postgres",
            "password": "your_password_here"
        },
        "redis": {
            "host": "localhost",
            "port": 6379
        },
        "test_scenarios": {
            "baseline_performance": {
                "enabled": True,
                "concurrent_connections": 20,
                "duration_minutes": 5,
                "description": "Baseline performance test"
            },
            "normal_load": {
                "enabled": True,
                "concurrent_connections": 50,
                "duration_minutes": 10,
                "description": "Normal operational load"
            },
            "peak_load": {
                "enabled": True,
                "concurrent_connections": 100,
                "duration_minutes": 15,
                "description": "Peak load simulation"
            },
            "stress_test": {
                "enabled": True,
                "concurrent_connections": 200,
                "duration_minutes": 20,
                "description": "Stress test"
            },
            "migration_load": {
                "enabled": True,
                "concurrent_users": 50,
                "duration_minutes": 10,
                "description": "Migration load test"
            }
        },
        "reporting": {
            "output_directory": "load_test_results",
            "generate_summary": True,
            "generate_charts": False,
            "include_raw_data": True
        }
    }
    return config

async def main():
    """Main function"""
    parser = argparse.ArgumentParser(description='Comprehensive Load Test Runner')
    parser.add_argument('--config', type=str, help='Path to configuration file')
    parser.add_argument('--create-config', type=str, help='Create sample configuration file')
    parser.add_argument('--scenarios', nargs='+', help='Run specific scenarios only')
    parser.add_argument('--output-dir', type=str, default='load_test_results', help='Output directory')
    parser.add_argument('--verbose', action='store_true', help='Enable verbose logging')
    
    args = parser.parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    # Create sample config if requested
    if args.create_config:
        config = create_sample_config()
        with open(args.create_config, 'w') as f:
            json.dump(config, f, indent=2)
        print(f"Sample configuration created: {args.create_config}")
        return
    
    # Run load tests
    orchestrator = LoadTestOrchestrator(args.config)
    
    # Override output directory if specified
    if args.output_dir:
        orchestrator.config["reporting"]["output_directory"] = args.output_dir
    
    # Filter scenarios if specified
    if args.scenarios:
        for scenario_name in orchestrator.config["test_scenarios"]:
            if scenario_name not in args.scenarios:
                orchestrator.config["test_scenarios"][scenario_name]["enabled"] = False
    
    try:
        report = await orchestrator.run_all_tests()
        
        print(f"\nComprehensive Load Testing Complete!")
        print(f"Total Duration: {report['test_suite_summary']['total_duration']:.1f} seconds")
        print(f"Scenarios Run: {report['test_suite_summary']['scenarios_run']}")
        print(f"Scenarios Passed: {report['test_suite_summary']['scenarios_passed']}")
        print(f"Scenarios Failed: {report['test_suite_summary']['scenarios_failed']}")
        
        if report["recommendations"]:
            print(f"\nTop Recommendations:")
            for rec in report["recommendations"][:3]:
                print(f"- [{rec['priority']}] {rec['recommendation']}")
        
        print(f"\nResults saved to: {orchestrator.config['reporting']['output_directory']}")
        
    except Exception as e:
        logger.error(f"Load testing failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())
