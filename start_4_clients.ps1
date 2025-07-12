# PowerShell script to run backend client in multiple terminals
# Updated to work with the optimized Hokm game

# Set the target folder (update this path as needed)
$targetFolder = "C:\Users\kasra\DS_project\backend"

# Command to run in each terminal - using direct execution instead of module
$runCommand = "cd `"$targetFolder`"; python client.py"

# Function to start a new PowerShell window with specific position and size
function Start-PositionedTerminal {
    param(
        [string]$Command,
        [int]$Left,
        [int]$Top,
        [int]$Width,
        [int]$Height
    )
    
    # Create a new PowerShell process with window positioning
    $processArgs = @(
        "-NoExit"
        "-Command"
        $Command
    )
    
    $process = Start-Process -FilePath "powershell.exe" -ArgumentList $processArgs -PassThru
    
    # Wait a moment for the window to appear
    Start-Sleep -Milliseconds 500
    
    # Use Windows API to position the window
    Add-Type -TypeDefinition @"
        using System;
        using System.Runtime.InteropServices;
        public class Win32 {
            [DllImport("user32.dll")]
            public static extern bool SetWindowPos(IntPtr hWnd, IntPtr hWndInsertAfter, int X, int Y, int cx, int cy, uint uFlags);
            [DllImport("user32.dll")]
            public static extern IntPtr FindWindow(string lpClassName, string lpWindowName);
            [DllImport("user32.dll")]
            public static extern bool ShowWindow(IntPtr hWnd, int nCmdShow);
        }
"@
    
    # Find the window by process ID (this is a simplified approach)
    $windowHandle = $process.MainWindowHandle
    if ($windowHandle -ne [IntPtr]::Zero) {
        [Win32]::SetWindowPos($windowHandle, [IntPtr]::Zero, $Left, $Top, $Width, $Height, 0x0040)
    }
    
    return $process
}

# Window bounds: {left, top, width, height}
# Adjusted for typical Windows screen resolution
$windowBounds = @(
    @{Left=100; Top=0; Width=640; Height=360},
    @{Left=740; Top=0; Width=640; Height=360},
    @{Left=100; Top=390; Width=640; Height=360},
    @{Left=740; Top=390; Width=640; Height=360}
)

Write-Host "🎮 Starting Hokm Game Client Terminals"
Write-Host "=" * 50

# Start 4 terminals with the specified positions
$processes = @()
foreach ($bounds in $windowBounds) {
    $process = Start-PositionedTerminal -Command $runCommand -Left $bounds.Left -Top $bounds.Top -Width $bounds.Width -Height $bounds.Height
    $processes += $process
    Start-Sleep -Milliseconds 300
}

Write-Host "✅ Started 4 Hokm game client terminals"
Write-Host "🎯 Each terminal will run: python client.py"
Write-Host "📍 Clients will connect to: ws://localhost:8765"
Write-Host ""
Write-Host "Press any key to close all terminals..."
$null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")

# Clean up - close all spawned processes
Write-Host "Closing all client terminals..."
foreach ($process in $processes) {
    if (!$process.HasExited) {
        $process.CloseMainWindow()
        if (!$process.WaitForExit(5000)) {
            $process.Kill()
        }
    }
}

Write-Host "🏁 All terminals closed"
