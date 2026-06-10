$OutputEncoding = [Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"
Set-Location "G:\E盘\工作项目文件\NAS\InfoRadar"
python ".\scripts\infobar_command.py" @args
exit $LASTEXITCODE
