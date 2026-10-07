param(
    [Parameter(Mandatory)][string]$Race,
    [Parameter(Mandatory)][string]$Track,
    [Parameter(Mandatory)][int]$Start,
    [Parameter(Mandatory)][int]$End,
    [int]$Divisions = 10000,
    [int]$Pass = 7,
    [string]$Output = "rpm-speed-ratio.png"
)

$plotArgs = @(
    "--x", "TrackPosition",
    "--y", "RPMperSpeed",
    "--type", "line",
    "--no-markers",
    "--gap-column", "Time",
    "--xlabel", "Track position",
    "--ylabel", "RPM / Speed",
    "--title", "RPM / Speed - pass $Pass",
    "--output", $Output
)

$passFilter = '$IntervalPass == ' + $Pass

python "$PSScriptRoot\aimcsv.py" $Race |
    python "$PSScriptRoot\track.py" --track-config $Track |
    python "$PSScriptRoot\interval.py" --start $Start --end $End --divisions $Divisions |
    mlr --csv filter $passFilter then filter '$Speed > 0' then put '$RPMperSpeed = $RPM / $Speed' |
    python "$PSScriptRoot\plot.py" @plotArgs