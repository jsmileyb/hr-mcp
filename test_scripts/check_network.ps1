#!/bin/bash
# Network diagnostic script for Windows (PowerShell)
# Save as check_network.ps1 and run with PowerShell

Write-Host "=== Network Diagnostic for HR-MCP ===" -ForegroundColor Green

# Test DNS resolution
Write-Host "`n--- DNS Resolution Test ---" -ForegroundColor Yellow
Measure-Command { Resolve-DnsName localhost } | Select-Object TotalMilliseconds
Measure-Command { Resolve-DnsName 127.0.0.1 } | Select-Object TotalMilliseconds

# Test TCP connectivity
Write-Host "`n--- TCP Connectivity Test ---" -ForegroundColor Yellow
Test-NetConnection -ComputerName localhost -Port 5001
Test-NetConnection -ComputerName 127.0.0.1 -Port 5001

# Test HTTP response time
Write-Host "`n--- HTTP Response Time Test ---" -ForegroundColor Yellow
$uri = "http://localhost:5001/docs"
try {
    $response = Measure-Command { Invoke-WebRequest -Uri $uri -UseBasicParsing }
    Write-Host "HTTP GET $uri took: $($response.TotalMilliseconds)ms"
} catch {
    Write-Host "HTTP GET failed: $($_.Exception.Message)" -ForegroundColor Red
}

# Check for proxy settings
Write-Host "`n--- Proxy Configuration ---" -ForegroundColor Yellow
$proxy = [System.Net.WebRequest]::GetSystemWebProxy()
Write-Host "System proxy: $($proxy.GetProxy('http://localhost:5001'))"

Write-Host "`n=== Diagnostic Complete ===" -ForegroundColor Green
