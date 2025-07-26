#!/usr/bin/env python3
# redis_cluster_setup.py
"""
Redis Cluster Setup and Management Script
"""

import os
import sys
import subprocess
import time
import argparse
import logging
from pathlib import Path
from typing import List, Dict, Any

from redis_cluster_config import (
    get_cluster_config, 
    generate_redis_config_file,
    generate_sentinel_config_file,
    generate_docker_compose_cluster,
    generate_k8s_deployment,
    detect_environment
)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class RedisClusterSetup:
    """Redis cluster setup and management utility"""
    
    def __init__(self, environment: str = None):
        self.environment = environment or detect_environment()
        self.config = get_cluster_config(self.environment)
        self.project_root = Path(__file__).parent.parent
        self.config_dir = self.project_root / "config" / "redis"
        
        # Ensure config directory exists
        self.config_dir.mkdir(parents=True, exist_ok=True)
    
    def generate_config_files(self):
        """Generate all Redis configuration files"""
        logger.info(f"Generating Redis configuration files for {self.environment} environment")
        
        # Generate Redis node configurations
        for i, node in enumerate(self.config.nodes):
            config_content = generate_redis_config_file(node)
            config_file = self.config_dir / f"redis-{node.port}.conf"
            
            with open(config_file, 'w') as f:
                f.write(config_content)
            
            logger.info(f"Generated Redis config: {config_file}")
        
        # Generate Sentinel configurations if configured
        if self.config.sentinel_nodes:
            for i, sentinel in enumerate(self.config.sentinel_nodes):
                config_content = generate_sentinel_config_file(sentinel, self.config.nodes[:3])
                config_file = self.config_dir / f"sentinel-{sentinel.port}.conf"
                
                with open(config_file, 'w') as f:
                    f.write(config_content)
                
                logger.info(f"Generated Sentinel config: {config_file}")
    
    def generate_docker_setup(self):
        """Generate Docker Compose setup"""
        logger.info("Generating Docker Compose setup")
        
        docker_compose = generate_docker_compose_cluster()
        compose_file = self.project_root / "docker-compose.redis-cluster.yml"
        
        with open(compose_file, 'w') as f:
            f.write(docker_compose)
        
        logger.info(f"Generated Docker Compose file: {compose_file}")
        
        # Create setup script
        setup_script = """#!/bin/bash
# Redis Cluster Docker Setup Script

set -e

echo "Setting up Redis Cluster with Docker..."

# Create config directory
mkdir -p config

# Copy config files
cp config/redis/*.conf config/

# Start the cluster
docker-compose -f docker-compose.redis-cluster.yml up -d

echo "Waiting for Redis nodes to start..."
sleep 15

# Initialize cluster
echo "Initializing Redis cluster..."
docker-compose -f docker-compose.redis-cluster.yml exec redis-1 \\
    redis-cli --cluster create \\
    redis-1:7000 redis-2:7001 redis-3:7002 \\
    redis-4:7003 redis-5:7004 redis-6:7005 \\
    --cluster-replicas 1 --cluster-yes

echo "Redis cluster setup complete!"
echo "Cluster status:"
docker-compose -f docker-compose.redis-cluster.yml exec redis-1 \\
    redis-cli --cluster info redis-1:7000

echo ""
echo "To connect to the cluster:"
echo "redis-cli -c -h localhost -p 7000"
"""
        
        setup_script_file = self.project_root / "setup-redis-cluster.sh"
        with open(setup_script_file, 'w') as f:
            f.write(setup_script)
        
        # Make executable
        os.chmod(setup_script_file, 0o755)
        logger.info(f"Generated setup script: {setup_script_file}")
    
    def generate_k8s_setup(self):
        """Generate Kubernetes setup"""
        logger.info("Generating Kubernetes setup")
        
        k8s_deployment = generate_k8s_deployment()
        k8s_file = self.project_root / "k8s-redis-cluster.yml"
        
        with open(k8s_file, 'w') as f:
            f.write(k8s_deployment)
        
        logger.info(f"Generated Kubernetes deployment: {k8s_file}")
        
        # Create setup script
        setup_script = """#!/bin/bash
# Redis Cluster Kubernetes Setup Script

set -e

echo "Setting up Redis Cluster on Kubernetes..."

# Apply the deployment
kubectl apply -f k8s-redis-cluster.yml

echo "Waiting for StatefulSet to be ready..."
kubectl wait --for=condition=ready pod -l app=redis-cluster --timeout=300s

echo "Waiting for cluster initialization job..."
kubectl wait --for=condition=complete job/redis-cluster-init --timeout=300s

echo "Redis cluster setup complete!"
echo "Cluster status:"
kubectl exec redis-cluster-0 -- redis-cli --cluster info redis-cluster-0.redis-cluster.default.svc.cluster.local:6379

echo ""
echo "To connect to the cluster:"
echo "kubectl port-forward svc/redis-cluster 6379:6379"
echo "redis-cli -c -h localhost -p 6379"
"""
        
        setup_script_file = self.project_root / "setup-redis-cluster-k8s.sh"
        with open(setup_script_file, 'w') as f:
            f.write(setup_script)
        
        # Make executable
        os.chmod(setup_script_file, 0o755)
        logger.info(f"Generated K8s setup script: {setup_script_file}")
    
    def start_local_cluster(self):
        """Start local Redis cluster for development"""
        logger.info("Starting local Redis cluster")
        
        if self.environment != "development":
            logger.error("Local cluster start only supported in development environment")
            return False
        
        # Check if Redis is installed
        try:
            subprocess.run(["redis-server", "--version"], 
                         check=True, capture_output=True)
        except (subprocess.CalledProcessError, FileNotFoundError):
            logger.error("Redis not found. Please install Redis first.")
            return False
        
        # Start Redis instances
        processes = []
        for node in self.config.nodes:
            config_file = self.config_dir / f"redis-{node.port}.conf"
            if not config_file.exists():
                logger.error(f"Config file not found: {config_file}")
                return False
            
            try:
                # Start Redis instance
                cmd = ["redis-server", str(config_file)]
                process = subprocess.Popen(cmd)
                processes.append(process)
                
                logger.info(f"Started Redis node {node.host}:{node.port} (PID: {process.pid})")
                time.sleep(1)  # Brief delay between starts
                
            except Exception as e:
                logger.error(f"Failed to start Redis node {node.host}:{node.port}: {e}")
                # Cleanup started processes
                for p in processes:
                    p.terminate()
                return False
        
        # Wait for nodes to start
        logger.info("Waiting for Redis nodes to start...")
        time.sleep(5)
        
        # Create cluster
        try:
            nodes_str = " ".join([f"{node.host}:{node.port}" for node in self.config.nodes])
            cmd = [
                "redis-cli", "--cluster", "create",
                *nodes_str.split(),
                "--cluster-replicas", "1",
                "--cluster-yes"
            ]
            
            result = subprocess.run(cmd, check=True, capture_output=True, text=True)
            logger.info("Cluster creation output:")
            logger.info(result.stdout)
            
            # Save process PIDs for cleanup
            pid_file = self.project_root / "redis-cluster.pids"
            with open(pid_file, 'w') as f:
                for process in processes:
                    f.write(f"{process.pid}\n")
            
            logger.info("Redis cluster started successfully!")
            logger.info(f"Process PIDs saved to: {pid_file}")
            
            return True
            
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to create cluster: {e}")
            logger.error(f"Error output: {e.stderr}")
            
            # Cleanup
            for process in processes:
                process.terminate()
            return False
    
    def stop_local_cluster(self):
        """Stop local Redis cluster"""
        logger.info("Stopping local Redis cluster")
        
        pid_file = self.project_root / "redis-cluster.pids"
        if not pid_file.exists():
            logger.warning("No PID file found. Cluster may not be running.")
            return
        
        try:
            with open(pid_file, 'r') as f:
                pids = [int(line.strip()) for line in f if line.strip()]
            
            for pid in pids:
                try:
                    os.kill(pid, 15)  # SIGTERM
                    logger.info(f"Terminated Redis process {pid}")
                except ProcessLookupError:
                    logger.warning(f"Process {pid} not found (already stopped)")
                except Exception as e:
                    logger.error(f"Failed to terminate process {pid}: {e}")
            
            # Remove PID file
            pid_file.unlink()
            logger.info("Local Redis cluster stopped")
            
        except Exception as e:
            logger.error(f"Failed to stop cluster: {e}")
    
    def status_check(self):
        """Check cluster status"""
        logger.info("Checking Redis cluster status")
        
        if not self.config.nodes:
            logger.error("No nodes configured")
            return
        
        first_node = self.config.nodes[0]
        
        try:
            # Get cluster info
            cmd = [
                "redis-cli", "-c", 
                "-h", first_node.host, 
                "-p", str(first_node.port),
                "--cluster", "info", f"{first_node.host}:{first_node.port}"
            ]
            
            result = subprocess.run(cmd, check=True, capture_output=True, text=True)
            logger.info("Cluster status:")
            print(result.stdout)
            
            # Get cluster nodes
            cmd = [
                "redis-cli", "-c",
                "-h", first_node.host,
                "-p", str(first_node.port),
                "cluster", "nodes"
            ]
            
            result = subprocess.run(cmd, check=True, capture_output=True, text=True)
            logger.info("Cluster nodes:")
            print(result.stdout)
            
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to get cluster status: {e}")
            logger.error(f"Error output: {e.stderr}")
    
    def cleanup(self):
        """Clean up cluster data and configurations"""
        logger.info("Cleaning up Redis cluster")
        
        # Stop local cluster if running
        self.stop_local_cluster()
        
        # Remove config files
        if self.config_dir.exists():
            import shutil
            shutil.rmtree(self.config_dir)
            logger.info(f"Removed config directory: {self.config_dir}")
        
        # Remove generated files
        generated_files = [
            "docker-compose.redis-cluster.yml",
            "k8s-redis-cluster.yml",
            "setup-redis-cluster.sh",
            "setup-redis-cluster-k8s.sh",
            "redis-cluster.pids"
        ]
        
        for filename in generated_files:
            file_path = self.project_root / filename
            if file_path.exists():
                file_path.unlink()
                logger.info(f"Removed: {file_path}")
        
        logger.info("Cleanup complete")

def main():
    parser = argparse.ArgumentParser(description="Redis Cluster Setup and Management")
    parser.add_argument("--env", choices=["development", "production", "single"],
                       help="Environment (auto-detected if not specified)")
    
    subparsers = parser.add_subparsers(dest="command", help="Available commands")
    
    # Setup commands
    subparsers.add_parser("generate-configs", help="Generate Redis configuration files")
    subparsers.add_parser("generate-docker", help="Generate Docker setup")
    subparsers.add_parser("generate-k8s", help="Generate Kubernetes setup")
    subparsers.add_parser("generate-all", help="Generate all configurations")
    
    # Management commands
    subparsers.add_parser("start", help="Start local Redis cluster")
    subparsers.add_parser("stop", help="Stop local Redis cluster")
    subparsers.add_parser("status", help="Check cluster status")
    subparsers.add_parser("cleanup", help="Clean up cluster data")
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return
    
    # Initialize setup manager
    setup = RedisClusterSetup(args.env)
    
    # Execute command
    try:
        if args.command == "generate-configs":
            setup.generate_config_files()
        elif args.command == "generate-docker":
            setup.generate_config_files()
            setup.generate_docker_setup()
        elif args.command == "generate-k8s":
            setup.generate_config_files()
            setup.generate_k8s_setup()
        elif args.command == "generate-all":
            setup.generate_config_files()
            setup.generate_docker_setup()
            setup.generate_k8s_setup()
        elif args.command == "start":
            setup.generate_config_files()
            setup.start_local_cluster()
        elif args.command == "stop":
            setup.stop_local_cluster()
        elif args.command == "status":
            setup.status_check()
        elif args.command == "cleanup":
            setup.cleanup()
        
    except KeyboardInterrupt:
        logger.info("Operation cancelled by user")
    except Exception as e:
        logger.error(f"Operation failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
