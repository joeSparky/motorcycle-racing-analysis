$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
Set-Location -LiteralPath $PSScriptRoot
$logStarted = $false
$result = 1
try {
    Start-Transcript -Path (Join-Path $PSScriptRoot 'setup-log.txt') -Force | Out-Null
    $logStarted = $true
    Write-Host 'Checking Python...' -ForegroundColor Cyan
    $python = $null
    $candidates = @()
    $py = Get-Command py.exe -ErrorAction SilentlyContinue
    if ($py) { $candidates += @{Exe=$py.Source; Args=@('-3')} }
    $plain = Get-Command python.exe -ErrorAction SilentlyContinue
    if ($plain -and $plain.Source -notlike '*\WindowsApps\*') {
        $candidates += @{Exe=$plain.Source; Args=@()}
    }
    foreach ($candidate in $candidates) {
        $exe = $candidate.Exe
        $prefix = $candidate.Args
        $found = & $exe @prefix -c 'import sys; print(sys.executable) if sys.version_info >= (3,9) else sys.exit(1)' 2>$null
        if ($LASTEXITCODE -eq 0 -and $found) { $python = ($found | Select-Object -Last 1).Trim(); break }
    }
    if (-not $python) {
        throw 'Python 3.9 or newer was not found. Install 64-bit Python from https://www.python.org/downloads/windows/ with Tcl/Tk included and Add Python to PATH selected. Then run Setup.cmd again in your usual Windows account.'
    }
    & $python -c 'import tkinter'
    if ($LASTEXITCODE -ne 0) { throw 'Python is missing Tkinter. Modify or reinstall Python with Tcl/Tk support, then rerun Setup.cmd.' }
    Write-Host 'Preparing the local Python environment...' -ForegroundColor Cyan
    $venv = Join-Path $PSScriptRoot '.venv'
    $localPython = Join-Path $venv 'Scripts\python.exe'
    if (-not (Test-Path -LiteralPath $localPython)) {
        & $python -m venv $venv
        if ($LASTEXITCODE -ne 0) { throw 'Could not create the Python environment. Extract the ZIP into a writable folder such as Documents\Race Analysis.' }
    }
    & $localPython -m pip install --disable-pip-version-check matplotlib PyYAML numpy
    if ($LASTEXITCODE -ne 0) { throw 'Python package installation failed. Check your internet connection and rerun Setup.cmd.' }
    & $localPython -c 'import tkinter, matplotlib, yaml, numpy'
    if ($LASTEXITCODE -ne 0) { throw 'The Python package check failed.' }

    Write-Host 'Checking mpv...' -ForegroundColor Cyan
    $mpvPath = Join-Path $PSScriptRoot 'tools\mpv\mpv.exe'
    if (-not (Test-Path -LiteralPath $mpvPath)) {
        $existing = Get-Command mpv.exe -ErrorAction SilentlyContinue
        if ($existing) { $mpvPath = $existing.Source }
        else {
            Write-Host 'Downloading portable mpv. This may take several minutes...'
            $nativeArch = $env:PROCESSOR_ARCHITECTURE
            if ($env:PROCESSOR_ARCHITEW6432) { $nativeArch = $env:PROCESSOR_ARCHITEW6432 }
            $arch = switch ($nativeArch) { 'AMD64' {'x86_64'} 'ARM64' {'aarch64'} 'x86' {'i686'} default {throw "Unsupported processor: $nativeArch"} }
            $release = Invoke-RestMethod -Uri 'https://api.github.com/repos/shinchiro/mpv-winbuild-cmake/releases/latest' -Headers @{'User-Agent'='Race-Analysis-Setup'}
            $asset = $release.assets | Where-Object { $_.name -match "^mpv-$arch-[0-9].*\.7z$" } | Select-Object -First 1
            if (-not $asset) { throw 'A compatible mpv download was not found.' }
            $temp = Join-Path $PSScriptRoot ('download-' + [guid]::NewGuid().ToString('N'))
            New-Item -ItemType Directory -Path $temp | Out-Null
            try {
                $archive = Join-Path $temp 'mpv.7z'
                $extractor = Join-Path $temp '7zr.exe'
                Invoke-WebRequest -UseBasicParsing -Uri $asset.browser_download_url -OutFile $archive
                if ($asset.digest -and $asset.digest.StartsWith('sha256:')) {
                    if ((Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash.ToLowerInvariant() -ne $asset.digest.Substring(7).ToLowerInvariant()) { throw 'mpv download checksum mismatch. Run setup again.' }
                }
                Invoke-WebRequest -UseBasicParsing -Uri 'https://www.7-zip.org/a/7zr.exe' -OutFile $extractor
                $dest = Join-Path $PSScriptRoot 'tools\mpv'
                & $extractor x $archive "-o$dest" -y
                if ($LASTEXITCODE -ne 0) { throw 'Could not extract mpv.' }
                $mpvFile = Get-ChildItem -LiteralPath $dest -Recurse -Filter mpv.exe | Select-Object -First 1
                if (-not $mpvFile) { throw 'The download did not contain mpv.exe.' }
                $mpvPath = $mpvFile.FullName
            } finally { Remove-Item -LiteralPath $temp -Recurse -Force -ErrorAction SilentlyContinue }
        }
    }
    & $mpvPath --version
    if ($LASTEXITCODE -ne 0) { throw 'mpv was found but could not run.' }
    @{python=$localPython; mpv=$mpvPath} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $PSScriptRoot 'setup-settings.json') -Encoding UTF8
    Write-Host ''
    Write-Host 'SETUP COMPLETE: Python packages and mpv are ready.' -ForegroundColor Green
    Write-Host 'Double-click Race-Analysis.cmd to open the launcher.'
    Write-Host 'Keep this folder in its current location. No administrator privileges are needed.'
    $result = 0
} catch {
    Write-Host ''
    Write-Host ('SETUP STOPPED: ' + $_.Exception.Message) -ForegroundColor Red
} finally {
    if ($logStarted) { Stop-Transcript | Out-Null }
}
exit $result
