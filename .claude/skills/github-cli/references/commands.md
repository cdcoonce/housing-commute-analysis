# GitHub CLI Command Reference

Comprehensive reference for all gh commands used in GitHub workflows.

## Authentication

```bash
# Interactive login
gh auth login                             # Prompts for GitHub instance
gh auth login --hostname github.example.com

# Token-based login
gh auth login --with-token < token.txt
echo "ghp_xxxx" | gh auth login --with-token

# Check auth status
gh auth status
gh auth status --hostname github.example.com

# Refresh auth scopes
gh auth refresh --scopes repo,read:org

# Logout
gh auth logout
```

## Issue Commands

### gh issue create

```bash
# Basic creation
gh issue create -t "Bug: Login fails" -b "Steps to reproduce..."

# With metadata
gh issue create \
  -t "Feature: Dark mode" \
  -b "Implement dark theme support" \
  --label "enhancement,frontend" \
  --milestone "v2.0" \
  --assignee "username" \
  --project "Board Name"

# From a file
gh issue create -t "Title" --body-file description.md

# Interactive (prompts for all fields)
gh issue create
```

**Flags:**
- `-t, --title` - Issue title (required unless interactive)
- `-b, --body` - Issue description
- `-l, --label` - Labels (comma-separated)
- `-a, --assignee` - Assignee usernames (comma-separated)
- `-m, --milestone` - Milestone name
- `-p, --project` - Project board name
- `--body-file` - Read body from file
- `-w, --web` - Open in browser after creation
- `-R, --repo` - Target repository (OWNER/REPO)

### gh issue list

```bash
# Basic listing
gh issue list                             # Open issues
gh issue list --state all                 # All states
gh issue list --state closed              # Only closed

# Filtering
gh issue list --assignee @me
gh issue list --author username
gh issue list --label "bug"
gh issue list --label "bug,critical"      # Multiple labels (AND)
gh issue list --milestone "Sprint 1"
gh issue list --search "login error"

# Pagination
gh issue list --limit 50

# Output format
gh issue list --json number,title,state
gh issue list --json number,title --jq '.[].title'
```

### gh issue view

```bash
gh issue view 123                         # View in terminal
gh issue view 123 --web                   # Open in browser
gh issue view 123 --comments              # Include comments
gh issue view 123 --json title,body,labels
```

### gh issue edit

```bash
gh issue edit 123 --title "New title"
gh issue edit 123 --body "Updated description"
gh issue edit 123 --body-file updated.md
gh issue edit 123 --add-label "in-progress"
gh issue edit 123 --remove-label "todo"
gh issue edit 123 --add-assignee "newuser"
gh issue edit 123 --remove-assignee "olduser"
gh issue edit 123 --milestone "v2.0"
gh issue edit 123 --milestone ""          # Remove milestone
gh issue edit 123 --add-project "Board"
```

### gh issue comment

```bash
gh issue comment 123 -b "Comment text"
gh issue comment 123 --body-file comment.md
gh issue comment 123                      # Opens editor for comment
gh issue comment 123 --edit-last -b "Updated comment"
```

### gh issue close / reopen / delete

```bash
gh issue close 123
gh issue close 123 -c "Closing as duplicate of #100"
gh issue reopen 123
gh issue delete 123 --yes
```

### gh issue develop

```bash
# Create a linked branch for an issue
gh issue develop 123                      # Creates a branch linked to issue
gh issue develop 123 --name feature/auth  # Custom branch name
gh issue develop 123 --base develop       # Branch from specific base
```

## Pull Request Commands

### gh pr create

```bash
# Interactive creation
gh pr create

# Auto-fill from commits
gh pr create --fill
gh pr create --fill-first                 # Use first commit only

# Draft PR
gh pr create --draft
gh pr create --draft --fill

# Full specification
gh pr create \
  -t "feat: Add user authentication" \
  -b "Implements OAuth2 login flow" \
  -B main \
  -H feature/auth \
  --label "feature,security" \
  --assignee "@me" \
  --reviewer "senior-dev" \
  --milestone "v2.0"

# From a file
gh pr create -t "Title" --body-file description.md

# From different repo
gh pr create -R owner/other-repo

# Open in browser to continue editing
gh pr create --web
```

**Flags:**
- `-t, --title` - PR title
- `-b, --body` - PR description
- `-B, --base` - Base branch (default: repo default)
- `-H, --head` - Head branch (default: current branch)
- `-l, --label` - Labels (comma-separated)
- `-a, --assignee` - Assignees (comma-separated)
- `--reviewer` - Reviewers (comma-separated)
- `-m, --milestone` - Milestone
- `--draft` - Create as draft
- `--fill` - Auto-fill title/description from commits
- `--fill-first` - Use only first commit for auto-fill
- `--body-file` - Read body from file
- `--no-maintainer-edit` - Disallow maintainer edits
- `-w, --web` - Open in browser
- `-R, --repo` - Target repository (OWNER/REPO)

### gh pr list

```bash
# Basic listing
gh pr list                                # Open PRs
gh pr list --state all                    # All states
gh pr list --state merged                 # Only merged
gh pr list --state closed                 # Only closed

# Filtering
gh pr list --assignee @me                 # Assigned to you
gh pr list --author @me                   # Created by you
gh pr list --search "review-requested:@me"  # Awaiting your review
gh pr list --draft                        # Draft PRs only
gh pr list --label "needs-review"
gh pr list --head "feature/*"             # By head branch
gh pr list --base "main"                  # By base branch

# Output
gh pr list --json number,title,state
gh pr list --json number,title --jq '.[].title'
gh pr list --limit 50
```

### gh pr view

```bash
gh pr view 45                             # View in terminal
gh pr view 45 --web                       # Open in browser
gh pr view 45 --comments                  # Include discussion
gh pr view                                # Current branch's PR
gh pr view 45 --json title,body,reviews
```

### gh pr checkout

```bash
gh pr checkout 45                         # Checkout PR branch
gh pr checkout 45 -b my-local-branch      # Custom local branch name
gh pr checkout 45 --detach                # Detached HEAD
gh pr checkout 45 --force                 # Force checkout
gh pr checkout 45 --recurse-submodules    # Update submodules
```

### gh pr diff

```bash
gh pr diff 45                             # Show diff
gh pr diff                                # Current branch's PR
gh pr diff 45 --color=always | less -R    # Paged with colors
gh pr diff 45 --patch                     # Patch format
```

### gh pr edit

```bash
# Modify PR properties
gh pr edit 45 --title "New title"
gh pr edit 45 --body "Updated"
gh pr edit 45 --body-file updated.md
gh pr edit 45 --base develop
gh pr edit 45 --add-label "approved"
gh pr edit 45 --remove-label "wip"
gh pr edit 45 --add-assignee "newuser"
gh pr edit 45 --add-reviewer "reviewer1,reviewer2"
gh pr edit 45 --milestone "v2.0"
gh pr edit 45 --add-project "Board"

# Interactive mode
gh pr edit 45
gh pr edit                                # Current branch's PR
```

### gh pr ready / draft conversion

```bash
gh pr ready 45                            # Mark draft as ready for review
gh pr ready                               # Current branch's PR

# Note: gh does not have a direct "convert to draft" command.
# Use the GitHub web UI or API to convert a PR back to draft.
```

### gh pr review

```bash
# Approve
gh pr review 45 --approve
gh pr review 45 --approve -b "LGTM!"

# Request changes
gh pr review 45 --request-changes -b "Please fix error handling"

# Comment-only review
gh pr review 45 --comment -b "A few suggestions"

# Current branch's PR
gh pr review --approve
```

### gh pr merge

```bash
gh pr merge 45                            # Interactive merge
gh pr merge 45 --merge                    # Standard merge commit
gh pr merge 45 --squash                   # Squash commits
gh pr merge 45 --rebase                   # Rebase merge

# Post-merge actions
gh pr merge 45 --delete-branch            # Delete branch after merge
gh pr merge 45 --auto                     # Auto-merge when checks pass
gh pr merge 45 --auto --squash --delete-branch  # Common combo

# Customise commit message
gh pr merge 45 --subject "feat: auth" --body "Implements OAuth2"

# Current branch's PR
gh pr merge
gh pr merge --squash --delete-branch
```

### gh pr comment

```bash
gh pr comment 45 -b "Comment text"
gh pr comment 45 --body-file review.md
gh pr comment 45                          # Opens editor
gh pr comment -b "LGTM"                   # Current branch's PR
gh pr comment 45 --edit-last -b "Updated"
```

### gh pr close / reopen

```bash
gh pr close 45
gh pr close 45 -c "Superseded by #50"
gh pr close 45 --delete-branch            # Close and delete branch
gh pr reopen 45
```

### gh pr checks

```bash
gh pr checks 45                           # View status checks
gh pr checks                              # Current branch's PR
gh pr checks 45 --watch                   # Watch until complete
gh pr checks 45 --required                # Only required checks
gh pr checks 45 --fail-fast               # Exit on first failure
```

## GitHub Actions Commands

### gh run list

```bash
gh run list                               # Recent runs
gh run list --workflow ci.yml             # Specific workflow
gh run list --branch main                 # Specific branch
gh run list --status failure              # Failed runs
gh run list --user @me                    # Your triggered runs
gh run list --limit 20
gh run list --json databaseId,status,conclusion
```

### gh run view

```bash
gh run view                               # Interactive selector
gh run view 12345                         # Specific run
gh run view 12345 --web                   # Open in browser
gh run view 12345 --log                   # Full log output
gh run view 12345 --log-failed            # Only failed job logs
gh run view 12345 --exit-status           # Exit with run's status code
gh run view 12345 --json jobs
```

### gh workflow run

```bash
gh workflow run ci.yml                    # Trigger on default branch
gh workflow run ci.yml --ref feature/x    # Specific branch/tag
gh workflow run ci.yml -f key=value       # Input parameters
gh workflow run ci.yml -F key=@file.txt   # Input from file
```

### gh run rerun

```bash
gh run rerun 12345                        # Re-run all jobs
gh run rerun 12345 --failed               # Re-run only failed jobs
gh run rerun 12345 --debug                # Re-run with debug logging
```

### gh run watch

```bash
gh run watch                              # Watch most recent run
gh run watch 12345                        # Watch specific run
gh run watch --exit-status                # Exit with run's status code
```

### gh run cancel

```bash
gh run cancel 12345                       # Cancel a running workflow
```

### gh workflow list / view / enable / disable

```bash
gh workflow list                          # All workflows
gh workflow view ci.yml                   # Workflow details
gh workflow enable ci.yml                 # Enable disabled workflow
gh workflow disable ci.yml                # Disable workflow
```

## Repository Commands

### gh repo clone

```bash
gh repo clone owner/repo
gh repo clone owner/repo target-dir
gh repo clone owner/repo -- --depth=1     # Shallow clone
```

### gh repo view

```bash
gh repo view                              # Current repo
gh repo view owner/repo
gh repo view --web                        # Open in browser
gh repo view --json name,description,defaultBranchRef
```

### gh repo fork

```bash
gh repo fork owner/repo
gh repo fork owner/repo --clone           # Fork and clone
gh repo fork --remote                     # Add fork as remote
```

### gh repo create

```bash
gh repo create my-repo --public
gh repo create my-repo --private
gh repo create my-repo --private --clone  # Create and clone
gh repo create --source .                 # From existing local repo
gh repo create --template owner/template  # From template
```

## Release Commands

```bash
# Create release
gh release create v1.0.0
gh release create v1.0.0 --title "v1.0.0" --notes "Release notes"
gh release create v1.0.0 --notes-file CHANGELOG.md
gh release create v1.0.0 --generate-notes   # Auto-generate from commits
gh release create v1.0.0 --draft            # Draft release
gh release create v1.0.0 --prerelease       # Pre-release
gh release create v1.0.0 ./dist/*           # Upload assets

# List / view
gh release list
gh release view v1.0.0
gh release view v1.0.0 --web

# Download assets
gh release download v1.0.0
gh release download v1.0.0 --pattern '*.tar.gz'

# Delete
gh release delete v1.0.0 --yes
```

## Configuration

### gh config

```bash
# View config
gh config list
gh config get editor

# Set config
gh config set editor vim
gh config set browser firefox
gh config set git_protocol ssh
gh config set prompt disabled

# Per-host config
gh config set -h github.example.com git_protocol ssh
```

### Aliases

```bash
# Create alias
gh alias set co 'pr checkout'
gh alias set review 'pr list --search "review-requested:@me"'
gh alias set pv 'pr view --web'

# List aliases
gh alias list

# Delete alias
gh alias delete co
```

## Tips & Patterns

### Complete Feature Branch Workflow

```bash
# 1. Create feature branch from issue
gh issue develop 123 --name feature/issue-123-add-auth

# 2. Make changes and commit
git add .
git commit -m "feat: add OAuth2 authentication

Implements login flow with:
- Google OAuth2 provider
- Session management
- Token refresh

Closes #123"

# 3. Push and create draft PR
git push -u origin feature/issue-123-add-auth
gh pr create --draft --fill

# 4. Continue working, push updates
git add .
git commit -m "fix: handle token expiration"
git push

# 5. Mark ready for review
gh pr ready
gh pr edit --add-reviewer "senior-dev"

# 6. After approval, merge
gh pr merge --squash --delete-branch
```

### Quick Review Workflow

```bash
# 1. See pending reviews
gh pr list --search "review-requested:@me"

# 2. Checkout and test
gh pr checkout 45

# 3. Review diff
gh pr diff 45

# 4. Add feedback or approve
gh pr review 45 --approve -b "Looks good, minor nit on line 42"
```

### Batch Operations

```bash
# Close all PRs with specific label
gh pr list --label "stale" --json number --jq '.[].number' | xargs -I {} gh pr close {}

# Approve multiple PRs
for pr in 10 11 12; do gh pr review $pr --approve; done
```

### JSON Output & Filtering

```bash
# gh supports --json and --jq for structured output
gh issue list --json number,title,labels --jq '.[] | "\(.number): \(.title)"'
gh pr list --json number,headRefName --jq '.[] | select(.headRefName | startswith("feature/"))'
gh run list --json databaseId,status --jq '.[] | select(.status == "failure") | .databaseId'
```
