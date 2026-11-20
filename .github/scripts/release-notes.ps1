function Get-ReleaseTagMessage {
    $gitApi = "$env:GITHUB_API_URL/repos/$env:GITHUB_REPOSITORY/git"
    $tagName = [Uri]::EscapeDataString($env:GITHUB_REF_NAME)
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
        throw "Tag '$env:GITHUB_REF_NAME' no longer points to the workflow commit."
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
