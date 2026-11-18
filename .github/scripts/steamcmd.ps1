function Install-SteamCmd {
    $steamCmdDir = Join-Path $env:RUNNER_TEMP 'steamcmd'
    $archive = Join-Path $env:RUNNER_TEMP 'steamcmd.zip'
    Invoke-WebRequest -Uri 'https://steamcdn-a.akamaihd.net/client/installer/steamcmd.zip' -OutFile $archive
    Expand-Archive -LiteralPath $archive -DestinationPath $steamCmdDir
    $steamCmd = Join-Path $steamCmdDir 'steamcmd.exe'

    # The bootstrapper can return a nonzero exit code when it restarts after updating.
    $bootstrap = Start-Process -FilePath $steamCmd -ArgumentList '+quit' -WorkingDirectory $steamCmdDir -WindowStyle Hidden -Wait -PassThru
    Write-Output "SteamCMD bootstrap exit code: $($bootstrap.ExitCode)"

    Push-Location -LiteralPath $steamCmdDir
    try {
        & $steamCmd +quit
        if ($LASTEXITCODE -ne 0) {
            throw "The installed SteamCMD client failed to start (exit code $LASTEXITCODE)."
        }
    } finally {
        Pop-Location
    }
}

function Publish-SteamWorkshopItem {
    param([Parameter(Mandatory)][string]$WorkshopVdf)

    if (-not $env:STEAM_USERNAME -or -not $env:STEAM_CONFIG_VDF_B64) {
        throw 'Set STEAM_USERNAME and STEAM_CONFIG_VDF_B64 in the steam-workshop environment.'
    }

    $steamCmdDir = Join-Path $env:RUNNER_TEMP 'steamcmd'
    $configDir = Join-Path $steamCmdDir 'config'
    $configFile = Join-Path $configDir 'config.vdf'
    New-Item -ItemType Directory -Force -Path $configDir | Out-Null
    Push-Location -LiteralPath $steamCmdDir
    try {
        [IO.File]::WriteAllBytes($configFile, [Convert]::FromBase64String($env:STEAM_CONFIG_VDF_B64))
        $env:STEAM_CONFIG_VDF_B64 = $null

        $commands = @('+login', $env:STEAM_USERNAME, '+workshop_build_item', $WorkshopVdf, '+quit')
        $result = & (Join-Path $steamCmdDir 'steamcmd.exe') @commands 2>&1
        $exitCode = $LASTEXITCODE
        $output = $result -join "`n"

        if ($output -notmatch 'Logging in using cached credentials\.' -or
            $output -notmatch 'Logging in user .* to Steam Public\.\.\.OK') {
            throw "SteamCMD did not authenticate using the restored login cache (exit code $exitCode)."
        }
        Write-Output 'SteamCMD authenticated using the restored login cache.'

        if ($exitCode -ne 0 -or $output -notmatch 'Committing update\.\.\.Success') {
            throw "SteamCMD did not commit the Workshop update (exit code $exitCode)."
        }
        $workshopLog = Join-Path $steamCmdDir 'logs\workshop_log.txt'
        if (Select-String -LiteralPath $workshopLog -SimpleMatch 'No content change detected' -Quiet -ErrorAction SilentlyContinue) {
            Write-Output 'Steam accepted the update and reused the identical Workshop content.'
        } else {
            Write-Output 'SteamCMD committed the Workshop update.'
        }
    } finally {
        Remove-Item -LiteralPath $configFile -ErrorAction SilentlyContinue
        Pop-Location
    }
}
