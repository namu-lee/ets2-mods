function Get-ReleaseTagMessage([string]$ReleaseTag = $env:GITHUB_REF_NAME) {
    $gitApi = "$env:GITHUB_API_URL/repos/$env:GITHUB_REPOSITORY/git"
    $tagName = [Uri]::EscapeDataString($ReleaseTag)
    $request = @{
        Headers = @{
            Accept = 'application/vnd.github+json'
            Authorization = "Bearer $env:GH_TOKEN"
        }
        ErrorAction = 'Stop'
    }

    $target = (Invoke-RestMethod @request -Uri "$gitApi/ref/tags/$tagName").object
    $annotation = $null
    while ($target.type -eq 'tag') {
        $tag = Invoke-RestMethod @request -Uri "$gitApi/tags/$($target.sha)"
        $annotation ??= $tag
        $target = $tag.object
    }
    if ($target.sha -ne $env:GITHUB_SHA) {
        throw "Tag '$ReleaseTag' no longer points to the workflow commit."
    }
    if ($null -eq $annotation) {
        return ''
    }

    $message = [string]$annotation.message
    $signature = $annotation.verification.signature
    if ($signature -and $message.EndsWith($signature, [StringComparison]::Ordinal)) {
        $message = $message.Substring(0, $message.Length - $signature.Length)
    }
    return $message.TrimEnd("`r`n".ToCharArray())
}
