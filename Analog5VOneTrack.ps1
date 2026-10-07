param(
    [Parameter(Mandatory)][string]$Race,
    [Parameter(Mandatory)][string]$Track,
    [Parameter(Mandatory)][int]$Start,
    [Parameter(Mandatory)][int]$End,
    [int]$Divisions = 10000,
    [int]$Pass = 7,
    [string]$Output = "suspension.png"
)

$plotArgs = @(
    "--x", "TrackPosition",
    "--y", "Analog5V",
    "--type", "line",
    "--no-markers",
    "--gap-column", "Time",
    "--xlabel", "Track position",
    "--ylabel", "Analog5V",
    "--title", "Analog5V - pass $Pass",
    "--output", $Output
)

$passFilter = '$IntervalPass == ' + $Pass

python "$PSScriptRoot\aimcsv.py" $Race |
    python "$PSScriptRoot\track.py" --track-config $Track |
    python "$PSScriptRoot\interval.py" --start $Start --end $End --divisions $Divisions |
    mlr --csv filter $passFilter |
    python "$PSScriptRoot\plot.py" @plotArgs