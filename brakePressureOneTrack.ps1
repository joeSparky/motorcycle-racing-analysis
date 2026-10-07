param(
    [Parameter(Mandatory)][string]$Race,
    [Parameter(Mandatory)][string]$Track,
    [Parameter(Mandatory)][int]$Start,
    [Parameter(Mandatory)][int]$End,
    [int]$Divisions = 10000,
    [int]$Pass = 7,
    [string]$Output = "brake-pressure.png"
)

$plotArgs = @(
    "--x", "TrackPosition",
    "--y", "BrakePressure",
    "--type", "line",
    "--no-markers",
    "--gap-column", "Time",
    "--xlabel", "Track position",
    "--ylabel", "Brake pressure",
    "--title", "Brake pressure - pass $Pass",
    "--output", $Output
)

$passFilter = '$IntervalPass == ' + $Pass

python "$PSScriptRoot\aimcsv.py" $Race |
    python "$PSScriptRoot\track.py" --track-config $Track |
    python "$PSScriptRoot\interval.py" --start $Start --end $End --divisions $Divisions |
    mlr --csv filter $passFilter |
    python "$PSScriptRoot\plot.py" @plotArgs