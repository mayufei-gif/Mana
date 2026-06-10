param(
    [Parameter(Mandatory = $true)]
    [string]$VideoDir,

    [string]$ApiBase = "http://127.0.0.1:8000",

    [int]$TimeoutSeconds = 1800
)

$OutputEncoding = [Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)
$ErrorActionPreference = "Stop"

if (!(Test-Path -LiteralPath $VideoDir)) {
    throw "视频目录不存在：$VideoDir"
}

$ResolvedVideoDir = (Resolve-Path -LiteralPath $VideoDir).Path

function Normalize-PathText {
    param([Parameter(Mandatory = $true)][string]$PathText)
    return ([System.IO.Path]::GetFullPath($PathText)).TrimEnd("\", "/").Replace("/", "\")
}

function Get-StreamStatusCode {
    param([Parameter(Mandatory = $true)][string]$Uri)
    $response = $null
    try {
        $request = [System.Net.HttpWebRequest]::Create($Uri)
        $request.Method = "GET"
        $request.AllowAutoRedirect = $false
        $request.AddRange(0, 1)
        $response = $request.GetResponse()
        return [int]$response.StatusCode
    } catch [System.Net.WebException] {
        if ($_.Exception.Response) {
            $response = $_.Exception.Response
            return [int]$response.StatusCode
        }
        throw
    } finally {
        if ($response) {
            $response.Close()
        }
    }
}

function Invoke-JsonUtf8 {
    param(
        [Parameter(Mandatory = $true)][string]$Uri,
        [Parameter(Mandatory = $true)][string]$Method,
        [byte[]]$Body = $null
    )

    $parameters = @{
        Uri = $Uri
        Method = $Method
        UseBasicParsing = $true
    }
    if ($Body) {
        $parameters.Body = $Body
        $parameters.ContentType = "application/json; charset=utf-8"
    }
    $response = Invoke-WebRequest @parameters
    if ($response.RawContentStream) {
        $response.RawContentStream.Position = 0
        $reader = [System.IO.StreamReader]::new($response.RawContentStream, [System.Text.Encoding]::UTF8)
        try {
            return ($reader.ReadToEnd() | ConvertFrom-Json)
        } finally {
            $reader.Dispose()
        }
    }
    return ($response.Content | ConvertFrom-Json)
}

$NormalizedVideoDir = Normalize-PathText -PathText $ResolvedVideoDir
$scanBody = @{ video_dir = $ResolvedVideoDir } | ConvertTo-Json -Compress
$scanBodyBytes = [System.Text.Encoding]::UTF8.GetBytes($scanBody)
Write-Output "1. 扫描视频目录：$VideoDir"
$scan = Invoke-JsonUtf8 -Uri "$ApiBase/api/videos/scan" -Method POST -Body $scanBodyBytes
$scan | ConvertTo-Json -Depth 8

Write-Output "2. 读取课程库，选择最新入库且未缺失的视频"
$videosPayload = Invoke-JsonUtf8 -Uri "$ApiBase/api/videos" -Method GET
$video = $videosPayload.data |
    Where-Object {
        $_.missing -eq 0 -and
        (Normalize-PathText -PathText $_.file_path).StartsWith($NormalizedVideoDir, [System.StringComparison]::OrdinalIgnoreCase)
    } |
    Sort-Object id -Descending |
    Select-Object -First 1
if (!$video) {
    throw "没有在该目录发现可处理视频。"
}
Write-Output ("video_id={0} title={1} status={2}" -f $video.id, $video.title, $video.status)

if ($video.status -ne "ready" -or $video.subtitle_status -ne "ready") {
    Write-Output "3.1 验证未完成处理时 /stream 返回 409"
    $notReadyStreamStatus = Get-StreamStatusCode -Uri "$ApiBase/api/videos/$($video.id)/stream"
    if ($notReadyStreamStatus -ne 409) {
        throw "未完成视频的 /stream 状态异常：期望 409，实际 $notReadyStreamStatus"
    }
}

Write-Output "3. 加入优先处理队列"
$job = Invoke-JsonUtf8 -Uri "$ApiBase/api/videos/$($video.id)/priority-process" -Method POST
$job | ConvertTo-Json -Depth 8

Write-Output "4. 轮询处理状态"
$deadline = (Get-Date).AddSeconds($TimeoutSeconds)
while ((Get-Date) -lt $deadline) {
    Start-Sleep -Seconds 5
    $status = Invoke-JsonUtf8 -Uri "$ApiBase/api/videos/$($video.id)/status" -Method GET
    $v = $status.data.video
    $j = $status.data.job
    Write-Output ("{0} video={1} subtitle={2} step={3} progress={4}" -f (Get-Date -Format "HH:mm:ss"), $v.status, $v.subtitle_status, $j.current_step, $j.progress)
    if ($v.status -eq "ready" -and $v.subtitle_status -eq "ready") {
        break
    }
    if ($v.status -in @("failed", "missing")) {
        $stage = $v.error_stage
        $message = $v.error_message
        throw "处理失败：stage=$stage message=$message"
    }
}

$final = Invoke-JsonUtf8 -Uri "$ApiBase/api/videos/$($video.id)/status" -Method GET
$finalVideo = $final.data.video
if ($finalVideo.status -ne "ready" -or $finalVideo.subtitle_status -ne "ready") {
    throw "等待超时：视频尚未 ready。"
}

Write-Output "5. 验证字幕、章节、重点、播放 gating"
$subtitle = Invoke-JsonUtf8 -Uri "$ApiBase/api/videos/$($video.id)/transcript" -Method GET
$chapters = Invoke-JsonUtf8 -Uri "$ApiBase/api/videos/$($video.id)/chapters" -Method GET
$highlights = Invoke-JsonUtf8 -Uri "$ApiBase/api/videos/$($video.id)/highlights" -Method GET
$streamStatusCode = Get-StreamStatusCode -Uri "$ApiBase/api/videos/$($video.id)/stream"
if ($streamStatusCode -notin @(200, 206)) {
    throw "ready 后 /stream 状态异常：$streamStatusCode"
}

[pscustomobject]@{
    video_id = $video.id
    title = $finalVideo.title
    status = $finalVideo.status
    subtitle_status = $finalVideo.subtitle_status
    subtitle_segments = @($subtitle.data).Count
    chapters = @($chapters.data).Count
    highlights = @($highlights.data).Count
    stream_status = $streamStatusCode
} | ConvertTo-Json -Depth 8

Write-Output "真实视频烟雾测试通过。"
