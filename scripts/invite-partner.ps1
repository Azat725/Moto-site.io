<#
  Invite a partner-developer to the repository as a collaborator.

  Usage:
    ./scripts/invite-partner.ps1 -Login partner-github-login
    ./scripts/invite-partner.ps1 -Login partner-github-login -Permission maintain

  Requires GitHub CLI (gh) and `gh auth login` done by the repository owner.
  The partner gets an e-mail and can accept the invitation by the link printed below.
#>
param(
  [Parameter(Mandatory = $true)][string]$Login,
  [ValidateSet('pull', 'triage', 'push', 'maintain', 'admin')][string]$Permission = 'push'
)

$ErrorActionPreference = 'Stop'

if (-not (Get-Command gh -ErrorAction SilentlyContinue)) {
  throw 'GitHub CLI (gh) is not installed. Run: winget install --id GitHub.cli'
}

$repo = gh repo view --json nameWithOwner -q .nameWithOwner
if (-not $repo) { throw 'Run this script inside the cloned repository.' }

gh api -X PUT "repos/$repo/collaborators/$Login" -f permission=$Permission | Out-Null

Write-Host "Invitation sent to '$Login' with permission '$Permission'."
Write-Host "Link for the partner to accept: https://github.com/$repo/invitations"
Write-Host "Repository: https://github.com/$repo"
