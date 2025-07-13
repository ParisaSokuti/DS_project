# 🧪 Manual Fault Tolerance Testing Guide

## **Current System Status** ✅
- **Primary Server**: 🔴 Killed (port 8765) 
- **Secondary Server**: 🟢 Running (port 8766)
- **Load Balancer**: 🟢 Running (port 8760)
- **Client**: 🟢 Connected via load balancer to secondary server

## **Testing Methods During Active Game**

### **Method 1: Server Process Termination** ⚡
Kill server processes to simulate crashes:

```powershell
# Find Python processes
Get-Process python

# Kill primary server (if running)
taskkill /PID [PRIMARY_PID] /F

# Kill secondary server (if running)
taskkill /PID [SECONDARY_PID] /F

# Kill load balancer (if running)
taskkill /PID [LOAD_BALANCER_PID] /F
```

### **Method 2: Network Disconnection** 🌐
Simulate network issues by blocking ports:

```powershell
# Block primary server port
netsh advfirewall firewall add rule name="Block_Primary_Hokm" dir=in action=block protocol=TCP localport=8765

# Block secondary server port  
netsh advfirewall firewall add rule name="Block_Secondary_Hokm" dir=in action=block protocol=TCP localport=8766

# Restore connectivity
netsh advfirewall firewall delete rule name="Block_Primary_Hokm"
netsh advfirewall firewall delete rule name="Block_Secondary_Hokm"
```

### **Method 3: Redis Connection Disruption** 🗄️
Test Redis resilience:

```powershell
# Stop Redis service
net stop Redis

# Start Redis service
net start Redis

# Or restart Redis Docker container
docker restart redis-container
```

### **Method 4: Memory/CPU Stress Testing** 💾
Create resource exhaustion:

```powershell
# Start memory-intensive process
$array = @()
while($true) { $array += "x" * 1000000 }

# Or use PowerShell to consume CPU
1..100 | ForEach-Object -Parallel { while($true) { 1+1 } }
```

## **What to Watch During Testing** 👀

### **Load Balancer Logs** 
Monitor for these key events:
- ✅ Server health status changes
- 🔄 Connection routing decisions  
- ⚠️ Health check failures
- 📊 Server status summaries

### **Server Logs**
Look for:
- 🔌 New connections
- 💾 Redis operations
- 🎮 Game state changes
- ❌ Error handling

### **Client Behavior**
Observe:
- 🔄 Reconnection attempts
- 🎯 Seamless gameplay continuation
- ⚡ Response times
- 🚨 Error messages

## **Testing Scenarios** 🎯

### **Scenario A: Kill Primary During Authentication**
1. Start new client connection
2. Begin login process
3. Kill primary server mid-authentication
4. **Expected**: Client automatically routed to secondary server

### **Scenario B: Kill Server During Game Creation**
1. Create new game room
2. Kill active server during room setup
3. **Expected**: Game state preserved in Redis, failover occurs

### **Scenario C: Kill Server During Active Gameplay**
1. Start 4-player game
2. Play several rounds
3. Kill server during card play
4. **Expected**: Game continues on backup server

### **Scenario D: Kill Load Balancer**
1. Kill load balancer process
2. **Expected**: Clients lose connection but can reconnect directly to servers

### **Scenario E: Multiple Failures**
1. Kill primary server
2. Wait for failover
3. Kill secondary server
4. **Expected**: Complete service outage until restart

## **Recovery Testing** 🔄

### **Primary Server Recovery**
1. Restart primary server
2. **Expected**: Load balancer detects health restoration
3. **Expected**: New connections may route to primary again

### **Database Recovery**
1. Restart Redis
2. **Expected**: Servers reconnect automatically
3. **Expected**: Circuit breakers reset after successful connections

## **Monitoring Commands** 📊

### **Check Active Connections**
```powershell
netstat -ano | findstr :8760  # Load balancer
netstat -ano | findstr :8765  # Primary server
netstat -ano | findstr :8766  # Secondary server
```

### **Check Process Status**
```powershell
Get-Process python | Where-Object {$_.MainWindowTitle -match "server|load_balancer"}
```

### **Monitor Redis**
```powershell
redis-cli ping
redis-cli info replication
```

## **Expected Behaviors** ✅

### **Successful Failover Indicators**
- Load balancer marks failed server as unhealthy (🔴)
- New connections route to healthy servers only
- Existing connections maintain session state
- Game progression continues seamlessly
- Redis session data preserved

### **Recovery Indicators**
- Failed server marked healthy when restarted (🟢)
- Load balancer resumes routing to recovered server
- Circuit breakers reset to closed state
- Performance metrics return to normal

## **Emergency Commands** 🚨

### **Stop All Servers**
```powershell
Get-Process python | Stop-Process -Force
```

### **Reset Firewall Rules**
```powershell
netsh advfirewall firewall delete rule name=all program="python.exe"
```

### **Clear Redis Data**
```powershell
redis-cli FLUSHALL
```

## **Current Test Status** 📋
- ✅ Primary server failure simulated successfully
- ✅ Automatic failover to secondary server confirmed
- ✅ Load balancer health monitoring working
- ✅ Client connection routed to healthy secondary server
- 🎯 **Ready for live gameplay testing**

---

**🎮 You can now start a full 4-player game and test failover during actual gameplay!**
