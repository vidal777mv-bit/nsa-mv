@echo off
setlocal
cd /d "%~dp0"
powershell -NoProfile -Command "$ErrorActionPreference='Stop'; $url='http://127.0.0.1:8767/'; $server=$null; function Test-Atlas { try { $r=Invoke-WebRequest -UseBasicParsing -Uri $url -TimeoutSec 1 } catch { return $false }; if($r.Content -notmatch 'css/expedition.css' -or $r.Content -notmatch 'id=.propertyList.') { throw 'Port 8767 is serving a different site. Close that server or use another port.' }; return $true }; try { $ready=Test-Atlas; if(-not $ready) { $python=Join-Path (Get-Location).Path '.venv\Scripts\python.exe'; if(-not (Test-Path -LiteralPath $python)) { throw 'The project Python environment is missing: .venv\Scripts\python.exe' }; $site=Join-Path (Get-Location).Path 'site'; $serverArgs='-m http.server 8767 --bind 127.0.0.1 --directory ' + [char]34 + $site + [char]34; $server=Start-Process -FilePath $python -ArgumentList $serverArgs -WorkingDirectory (Get-Location).Path -WindowStyle Hidden -PassThru; $deadline=[DateTime]::UtcNow.AddSeconds(10); do { Start-Sleep -Milliseconds 150; $ready=Test-Atlas; if($ready -or $server.HasExited) { break } } while([DateTime]::UtcNow -lt $deadline) }; if(-not $ready) { throw 'The atlas server could not start. Check whether port 8767 is already occupied.' }; Start-Process $url } catch { if($server -and -not $server.HasExited) { Stop-Process -Id $server.Id -ErrorAction SilentlyContinue }; Write-Host $_.Exception.Message -ForegroundColor Red; exit 1 }"
if errorlevel 1 (
  echo.
  echo The atlas could not be opened. Review the message above.
  pause
  exit /b 1
)
endlocal

