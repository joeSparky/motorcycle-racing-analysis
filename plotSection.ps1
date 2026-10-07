# Example: .\plotSection.ps1 ../racingData/138.csv ../racingData/nelsonLedges.yaml 3
param(
    [Parameter(Position = 0)]
    [string]$Csv,

    [Parameter(Position = 1)]
    [string]$Yaml,

    [Parameter(Position = 2)]
    [ValidateRange(1, 2147483647)]
    [int]$Section,

    [ValidateRange(1, 2147483647)]
    [int[]]$Passes,

    [switch]$NoLegend,

    [string]$OutputDir = '.',

    [Alias('h')]
    [switch]$Help
)

if ($Help -or $PSBoundParameters.Count -eq 0) {
    @'
Plot rider paths through a track section.

Usage:
  .\plotSection.ps1 <race.csv> <track.yaml> <section> [options]

Parameters:
  -Csv         Rider race/practice CSV (AiM export or ordinary CSV).
  -Yaml        Track YAML configuration defining the reference and sections.
  -Section     Section number to plot (positive integer).
  -Passes      Optional pass numbers, e.g. -Passes 5,6. Default: all passes.
  -NoLegend    Hide the pass legend. Default: show legend.
  -OutputDir   Directory for the generated PNG. Created if needed.
               Default: current PowerShell directory.
  -h / -Help   Show this help without processing data.

Examples:
  .\plotSection.ps1 ../racingData/138.csv ../racingData/nelsonLedges.yaml 4
  .\plotSection.ps1 ../racingData/138.csv ../racingData/nelsonLedges.yaml 3 -Passes 5,6 -OutputDir ../racingResults/138

Outputs:
  All passes:      138-section4.png
  Selected passes: 138-section3-passes5-6.png

Tools:
  track.cmd and plot.cmd are found beside this script, then on PATH.
  mlr must be on PATH. Input paths are relative to the current directory.
'@
    return
}

$ErrorActionPreference = 'Stop'
if (-not $Csv -or -not $Yaml -or -not $PSBoundParameters.ContainsKey('Section')) {
    throw 'Supply -Csv, -Yaml and -Section (or three positional arguments). Use -h for help.'
}
if ([string]::IsNullOrWhiteSpace($OutputDir)) {
    throw '-OutputDir cannot be blank.'
}
function Find-Launcher([string]$Name) {
    $localPath = Join-Path $PSScriptRoot $Name
    if (Test-Path -LiteralPath $localPath -PathType Leaf) {
        return $localPath
    }
    return (Get-Command $Name -CommandType Application -ErrorAction Stop).Source
}
$csvPath = (Resolve-Path -LiteralPath $Csv).Path
$yamlPath = (Resolve-Path -LiteralPath $Yaml).Path
$trackCommand = Find-Launcher 'track.cmd'
$millerCommand = (Get-Command mlr -CommandType Application -ErrorAction Stop).Source
$plotCommand = Find-Launcher 'plot.cmd'
$sessionName = [System.IO.Path]::GetFileNameWithoutExtension($csvPath)
$outputFile = "$sessionName-section$Section.png"
$title = "$sessionName - Section $Section"
if ($Passes) {
    $Passes = @($Passes | Sort-Object -Unique)
    $passTag = $Passes -join '-'
    $outputFile = "$sessionName-section$Section-passes$passTag.png"
    $title += " - Passes " + ($Passes -join ', ')
}
$outputDirectory = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($OutputDir)
[System.IO.Directory]::CreateDirectory($outputDirectory) | Out-Null
$outputFile = Join-Path $outputDirectory $outputFile
$plotOptions = @()
if ($NoLegend) { $plotOptions += '--no-legend' }
$filter = '$Section == ' + $Section

if ($Passes) {
    $conditions = ($Passes | ForEach-Object { '$Pass == ' + $_ }) -join ' || '
    $filter += ' && (' + $conditions + ')'
}

& $trackCommand $csvPath --config $yamlPath |
    & $millerCommand --csv filter $filter |
    & $plotCommand --x "GPS Longitude" --y "GPS Latitude" --geo --type line --no-markers --gap-column Time --gap-max 1 --group Pass --line-width 2 `
        --title $title -o $outputFile @plotOptions

if ($LASTEXITCODE -ne 0) {
    throw "Section plotting failed with exit code $LASTEXITCODE."
}
