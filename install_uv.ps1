# Check if uv is already installed
try {
    # Refresh PATH to include any recently installed programs
    $env:PATH = [System.Environment]::GetEnvironmentVariable("PATH","Machine") + ";" + [System.Environment]::GetEnvironmentVariable("PATH","User")
    
    # Try to get uv version
    $uvVersion = uv --version 2>$null
    if ($uvVersion) {
        Write-Host "[SUCCESS] uv is already installed: $uvVersion" -ForegroundColor Green
        Write-Host "[INFO] No installation needed - you're all set!" -ForegroundColor Cyan
        exit 0
    }
} catch {
    # uv not found, continue with installation
}

Write-Host "[INFO] Installing uv..." -ForegroundColor Yellow

# Install uv using the official installer
try {
    powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
    
    # Refresh PATH after installation
    $env:PATH = [System.Environment]::GetEnvironmentVariable("PATH","Machine") + ";" + [System.Environment]::GetEnvironmentVariable("PATH","User")
    
    # Verify installation
    $uvVersion = uv --version
    Write-Host "[SUCCESS] Successfully installed uv: $uvVersion" -ForegroundColor Green
    
} catch {
    Write-Host "[ERROR] Failed to install uv: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}