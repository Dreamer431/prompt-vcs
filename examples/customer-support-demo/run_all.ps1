$ErrorActionPreference = "Stop"

$utf8 = New-Object System.Text.UTF8Encoding($false)
[Console]::InputEncoding = $utf8
[Console]::OutputEncoding = $utf8
$OutputEncoding = $utf8
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"

$demoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Push-Location -LiteralPath $demoRoot

try {
    Write-Host "`n[1/5] Run demo application" -ForegroundColor Cyan
    & python app.py
    if ($LASTEXITCODE -ne 0) { throw "Demo application failed" }

    Write-Host "`n[2/5] Run YAML prompt test suite" -ForegroundColor Cyan
    & python -m prompt_vcs.cli test "tests\prompt_suite.yaml" --project "."
    if ($LASTEXITCODE -ne 0) { throw "YAML prompt tests failed" }

    Write-Host "`n[3/5] Run Python unit tests for v1 and v2" -ForegroundColor Cyan
    & python -m unittest discover -s "tests" -p "test_*.py" -v
    if ($LASTEXITCODE -ne 0) { throw "Python unit tests failed" }

    Write-Host "`n[4/5] Validate mock response" -ForegroundColor Cyan
    $mockResponse = (Get-Content -LiteralPath "tests\mock_response.txt" -Encoding UTF8 -Raw).Trim()
    & python -m prompt_vcs.cli validate support_reply $mockResponse --config "tests\response_validation.yaml"
    if ($LASTEXITCODE -ne 0) { throw "Mock response validation failed" }

    Write-Host "`n[5/5] Show prompt diff between v1 and v2" -ForegroundColor Cyan
    & python -m prompt_vcs.cli diff support_reply v1 v2 --project "."
    if ($LASTEXITCODE -ne 0) { throw "Prompt version diff failed" }

    Write-Host "`nAll checks passed." -ForegroundColor Green
}
finally {
    Pop-Location
}
