param(
    [Parameter(Mandatory)][string]$Race,
    [Parameter(Mandatory)][string]$Track,
    [Parameter(Mandatory)][int]$Start,
    [Parameter(Mandatory)][int]$End,
    [int]$Divisions = 10000,
    [string]$Points,
    [string]$Output = "routes.png"
)

$plotArgs = @(
    "--x", "TrackX",
    "--y", "TrackY",
    "--type", "line",
    "--group", "IntervalPass",
    "--no-markers",
    "--gap-column", "Time",
    "--track-json", $Track,
    "--interval", "$Start-$End",
    "--output", $Output
)

if ($Points) {
    $plotArgs += @("--points-json", $Points)
}

python "$PSScriptRoot\aimcsv.py" $Race |
    python "$PSScriptRoot\track.py" --track-config $Track |
    python "$PSScriptRoot\interval.py" --start $Start --end $End --divisions $Divisions |
    python "$PSScriptRoot\plot.py" @plotArgs