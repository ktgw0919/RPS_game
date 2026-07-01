# GitHub post-setup (run after: gh auth login)
# Usage: .\scripts\github-post-setup.ps1

$ErrorActionPreference = "Stop"
$Repo = "ktgw0919/RPS_game"

if (-not (Get-Command gh -ErrorAction SilentlyContinue)) {
    Write-Error "GitHub CLI (gh) not found. Run: winget install GitHub.cli"
}

gh auth status 2>&1 | Out-Null
if ($LASTEXITCODE -ne 0) {
    Write-Error "Not logged in to gh. Run: gh auth login"
}

Write-Host "==> Labels"
$labels = @(
    @{ name = "enhancement"; color = "a2eeef"; description = "New feature or TODO Step" },
    @{ name = "bug"; color = "d73a4a"; description = "Bug report" },
    @{ name = "docs"; color = "0075ca"; description = "Documentation" },
    @{ name = "phase-3"; color = "7057ff"; description = "Phase 3 special rules" },
    @{ name = "mvp-polish"; color = "fbca04"; description = "MVP remaining tasks" }
)
foreach ($l in $labels) {
    $prev = $ErrorActionPreference
    $ErrorActionPreference = "SilentlyContinue"
    gh label create $l.name --color $l.color --description $l.description --repo $Repo 2>$null
    if ($LASTEXITCODE -ne 0) {
        gh label edit $l.name --color $l.color --description $l.description --repo $Repo 2>$null
    }
    $ErrorActionPreference = $prev
}

Write-Host "==> Milestones"
$milestones = @(
    @{ title = "Phase 3: Special Rules"; description = "docs/TODO.md Phase 3" },
    @{ title = "MVP polish"; description = "docs/TODO.md MVP remaining tasks" }
)
foreach ($m in $milestones) {
    gh api repos/$Repo/milestones -f title=$m.title -f description=$m.description 2>$null
    if ($LASTEXITCODE -ne 0) { Write-Host "  milestone $($m.title): may already exist" }
}

Write-Host "==> Branch protection (main)"
$protection = @{
    required_status_checks = @{
        strict   = $true
        contexts = @(
            "Backend (ruff / mypy / pytest)"
            "Frontend (eslint / prettier / build)"
        )
    }
    enforce_admins                = $true
    required_pull_request_reviews = @{ required_approving_review_count = 0 }
    restrictions                  = $null
} | ConvertTo-Json -Depth 5 -Compress

$protection | gh api repos/$Repo/branches/main/protection -X PUT --input -

if ($LASTEXITCODE -eq 0) {
    Write-Host "Branch protection applied."
} else {
    Write-Host "Branch protection failed. Re-run after CI passes, or set manually in Settings > Branches > main."
}

Write-Host "Done. Repository: https://github.com/$Repo"
