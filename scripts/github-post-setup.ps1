# GitHub 初回セットアップの残り（gh auth login 後に実行）
# Usage: .\scripts\github-post-setup.ps1

$ErrorActionPreference = "Stop"
$Repo = "ktgw0919/RPS_game"

if (-not (Get-Command gh -ErrorAction SilentlyContinue)) {
    Write-Error "GitHub CLI (gh) が見つかりません。winget install GitHub.cli を実行してください。"
}

gh auth status 2>&1 | Out-Null
if ($LASTEXITCODE -ne 0) {
    Write-Error "gh に未ログインです。gh auth login を実行してください。"
}

Write-Host "==> Labels"
$labels = @(
    @{ name = "enhancement"; color = "a2eeef"; description = "新機能・TODO Step" },
    @{ name = "bug"; color = "d73a4a"; description = "不具合" },
    @{ name = "docs"; color = "0075ca"; description = "ドキュメント" },
    @{ name = "phase-3"; color = "7057ff"; description = "Phase 3: 特殊ルール" },
    @{ name = "mvp-polish"; color = "fbca04"; description = "MVP 残タスク" }
)
foreach ($l in $labels) {
    gh label create $l.name --color $l.color --description $l.description --repo $Repo 2>$null
    if ($LASTEXITCODE -ne 0) { Write-Host "  label $($l.name): already exists or updated" }
}

Write-Host "==> Milestones"
$milestones = @(
    @{ title = "Phase 3: Special Rules"; description = "docs/TODO.md Phase 3" },
    @{ title = "MVP polish"; description = "docs/TODO.md MVP 残タスク" }
)
foreach ($m in $milestones) {
    gh api repos/$Repo/milestones -f title=$m.title -f description=$m.description 2>$null
    if ($LASTEXITCODE -ne 0) { Write-Host "  milestone $($m.title): may already exist" }
}

Write-Host "==> Branch protection (main)"
# CI ジョブ名は .github/workflows/ci.yml の jobs.*.name と一致させる
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
    Write-Host "Branch protection failed. CI が一度成功するまで required checks が選べない場合があります。"
    Write-Host "Settings > Branches > main で手動設定してください（CONTRIBUTING.md §2 参照）。"
}

Write-Host "Done. Repository: https://github.com/$Repo"
