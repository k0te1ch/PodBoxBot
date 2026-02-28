# setup_venvs.ps1
$services = @(
  ".\app\bot",
  ".\app\publisher\FTP",
  ".\app\kafka"
)

foreach ($service in $services) {
    Write-Host "=== Setup for $service ==="
    Set-Location $service

    if (-Not (Test-Path ".venv")) {
        Write-Host "Creating virtual environment in $service"
        python -m venv .venv
    }
    else {
        Write-Host "Virtual environment already exists in $service"
    }

    Write-Host "Upgrading pip inside $service/.venv"
    .\.venv\Scripts\python.exe -m pip install --upgrade pip

    Write-Host "Installing dependencies via poetry in $service"
    # Запускаем poetry через python.exe из venv, чтобы использовать локальное окружение
    .\.venv\Scripts\python.exe -m poetry install

    Write-Host "To activate virtual environment for $service, run:"
    Write-Host "  .\$service\.venv\Scripts\Activate.ps1"
    Write-Host ""

    Set-Location -Path $PSScriptRoot
}
