# Distributed Server Setup Guide
## High Availability Hokm Game with Two Machines

### Network Configuration
- **Primary Server**: Your machine (localhost)
- **Secondary Server**: Friend's machine (192.168.1.92)
- **Load Balancer**: Your machine (port 8760)
- **Both machines must be on the same WiFi network**

---

## Setup Instructions

### On Your Machine (Primary Server + Load Balancer)

#### 1. Start Primary Server
```bash
cd c:\Users\kasra\hokm_game
python backend/server.py --port 8765 --instance-name primary
```

#### 2. Start Load Balancer
```bash
cd c:\Users\kasra\hokm_game
python backend/load_balancer.py
```

#### 3. Start Redis Monitor (Optional)
```bash
cd c:\Users\kasra\hokm_game
python backend/redis_monitor.py
```

### On Friend's Machine (192.168.1.92) - Secondary Server

#### 1. Install Requirements
Make sure your friend has the same project setup:
```bash
# Copy the entire hokm_game folder to friend's machine
# Install requirements
pip install -r requirements.txt
```

#### 2. Configure Server for Network Access
Your friend needs to modify the server to listen on all interfaces.

Create this file on friend's machine: `start_secondary_server.py`
```python
#!/usr/bin/env python3
"""
Secondary server startup script for network access
"""
import asyncio
import sys
import os

# Add the backend directory to Python path
sys.path.append(os.path.join(os.path.dirname(__file__), 'backend'))

from server import GameServer

async def main():
    # Start server on all interfaces (0.0.0.0) so it's accessible from network
    server = GameServer(port=8765, instance_name="secondary")
    
    # Modify the server to listen on all interfaces
    print("🚀 Starting Secondary Server on 192.168.1.92:8765")
    print("📡 Accessible from network")
    
    # Start the server
    await server.start(host="0.0.0.0")  # Listen on all interfaces

if __name__ == "__main__":
    asyncio.run(main())
```

#### 3. Start Secondary Server
```bash
cd hokm_game
python start_secondary_server.py
```

### Network Configuration Notes

#### Firewall Settings (Important!)
Your friend's machine needs to allow incoming connections on port 8765:

**Windows Firewall:**
1. Open Windows Defender Firewall
2. Click "Allow an app or feature through Windows Defender Firewall"
3. Click "Change Settings" → "Allow another app"
4. Browse to Python executable and add it
5. Make sure both "Private" and "Public" are checked

**Alternative: Create specific rule:**
```cmd
# Run as Administrator
netsh advfirewall firewall add rule name="Hokm Game Server" dir=in action=allow protocol=TCP localport=8765
```

#### Network Testing
Test the connection from your machine:
```bash
# Test if friend's server is reachable
telnet 192.168.1.92 8765
# Or use PowerShell
Test-NetConnection -ComputerName 192.168.1.92 -Port 8765
```

---

## Testing the Setup

### 1. Verify Both Servers
- Primary server running on your machine (localhost:8765)
- Secondary server running on friend's machine (192.168.1.92:8765)
- Load balancer running on your machine (localhost:8760)

### 2. Start Clients
All clients connect to the load balancer on your machine:
```bash
cd c:\Users\kasra\hokm_game
python backend/client.py
```

### 3. Test Failover
1. Start a game with multiple players
2. While playing, stop the primary server (Ctrl+C)
3. Load balancer should detect failure and migrate to secondary server
4. Game should continue on friend's machine

---

## Expected Behavior

✅ **Normal Operation:**
- New clients connect to primary server (your machine)
- Load balancer shows: 🟢primary(X) 🟢secondary(0)

✅ **During Failover:**
- Primary server fails
- Load balancer detects failure within 2-4 seconds
- Existing connections migrate to secondary server (friend's machine)
- New connections go to secondary server
- Load balancer shows: 🔴primary(0) 🟢secondary(X)

✅ **Recovery:**
- Restart primary server
- New connections go back to primary
- Existing connections stay on secondary until they reconnect

---

## Troubleshooting

### Common Issues:

1. **Connection Refused to 192.168.1.92:8765**
   - Check firewall settings on friend's machine
   - Verify server is listening on 0.0.0.0, not just localhost
   - Test with `telnet 192.168.1.92 8765`

2. **Load Balancer Can't Reach Secondary**
   - Verify IP address is correct: `ping 192.168.1.92`
   - Check if port 8765 is open on friend's machine
   - Make sure both machines are on same WiFi network

3. **Migration Not Working**
   - Check load balancer logs for migration messages
   - Verify Redis is running on primary machine
   - Ensure secondary server has access to same Redis instance

### Network Diagnostics:
```bash
# On your machine, test connectivity
ping 192.168.1.92
telnet 192.168.1.92 8765

# Check if load balancer can see secondary server
# Look for "✅ Server secondary is now healthy" in load balancer logs
```

---

## Advanced: Shared Redis Setup

For best results, both servers should use the same Redis instance. You can either:

1. **Use Redis on your machine** (easier):
   - Friend's server connects to your Redis: `redis://YOUR_IP:6379`

2. **Set up Redis cluster** (more robust):
   - Run Redis on both machines with replication

Let me know if you need help with Redis configuration!
