param(
    [Parameter(Mandatory)][string]$Race,
    [Parameter(Mandatory)][string]$Track,
    [Parameter(Mandatory)][int]$Start,
    [Parameter(Mandatory)][int]$End,
    [int]$Divisions = 10000,
    [string]$Points)

$plotArgs = @(
    "--x", "TrackX",
    "--y", "TrackY",
    "--type", "line",
    "--group", "IntervalPass",
    "--no-markers",
    "--gap-column", "Time",
    "--track-json", $Track,
    "--interval", "$Start-$End"
)

if ($Points) {
    $plotArgs += @("--points-json", $Points)
}

python "$PSScriptRoot\aimcsv.py" $Race |
    python "$PSScriptRoot\track.py" --track-config $Track |
    python "$PSScriptRoot\interval.py" --start $Start --end $End --divisions $Divisions |
    python timing.py |
    ConvertFrom-Csv |
    Sort-Object { if ($_.BehindBest -eq '') { [double]::PositiveInfinity } else { [double]$_.BehindBest } } |
    Format-Table Pass, Lap, IntervalTime, BehindBest, Complete -AutoSize