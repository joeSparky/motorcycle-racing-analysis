# Usage: .\plotElevation.ps1 -Track ../racingData/NelsonLedges.csv
# The alias also accepts --track.
param(
    [Parameter(Mandatory = $true)]
    [Alias('-track')]
    [string]$Track
)

$ErrorActionPreference = 'Stop'
$trackPath = (Resolve-Path -LiteralPath $Track).Path
if (-not (Test-Path -LiteralPath $trackPath -PathType Leaf)) {
    throw "Track CSV is not a file: $Track"
}
$trackName = [System.IO.Path]::GetFileNameWithoutExtension($trackPath)
$outputFile = Join-Path (Get-Location).Path "$trackName-elevation.png"

# Prefer the plot.cmd launcher beside this script, then one on PATH.
$localLauncher = Join-Path $PSScriptRoot 'plot.cmd'
if (Test-Path -LiteralPath $localLauncher -PathType Leaf) {
    $plotCommand = $localLauncher
} else {
    $plotCommand = (Get-Command plot.cmd -ErrorAction Stop).Source
}

& $plotCommand $trackPath `
  --x longitude_deg --y latitude_deg `
  --color elevation_m_inferred `
  --color-label "Elevation (m; inferred units)" `
  --fill-closed-color --type line --line-width 4 `
  --geo --xlabel Longitude --ylabel Latitude `
  --title "$trackName elevation" `
  -o $outputFile

if ($LASTEXITCODE -ne 0) {
    throw "Plotting failed with exit code $LASTEXITCODE."
}
