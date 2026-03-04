# GitLab CLI Command Reference

Comprehensive reference for all glab commands used in GitLab workflows.

## Authentication

```bash
# Interactive login
glab auth login                           # Prompts for GitLab instance
glab auth login --hostname gitlab.example.com

# Token-based login
glab auth login --token glpat-xxxx
glab auth login --stdin < token.txt

# Check auth status
glab auth status
glab auth status --hostname gitlab.example.com

# Logout
glab auth logout
```

## Issue Commands

### glab issue create

```bash
# Basic creation
glab issue create -t "Bug: Login fails" -d "Steps to reproduce..."

# With metadata
glab issue create \
  -t "Feature: Dark mode" \
  -d "Implement dark theme support" \
  --label="enhancement,frontend" \
  --milestone="v2.0" \
  --assignee="username" \
  --confidential

# Interactive (prompts for all fields)
glab issue create
```

**Flags:**
- `-t, --title` - Issue title (required unless interactive)
- `-d, --description` - Issue description
- `-l, --label` - Labels (comma-separated)
- `-a, --assignee` - Assignee usernames (comma-separated)
- `-m, --milestone` - Milestone name or ID
- `--confidential` - Mark as confidential
- `--weight` - Issue weight (if enabled)
- `--web` - Open in browser after creation

### glab issue list

```bash
# Basic listing
glab issue list                           # Open issues
glab issue list --all                     # All states
glab issue list --closed                  # Only closed

# Filtering
glab issue list --assignee=@me
glab issue list --author=username
glab issue list --label="bug"
glab issue list --label="bug,critical"    # Multiple labels (AND)
glab issue list --milestone="Sprint 1"
glab issue list --search="login error"

# Pagination
glab issue list --per-page=50
glab issue list --page=2

# Output format
glab issue list --output=json
```

### glab issue view

```bash
glab issue view 123                       # View in terminal
glab issue view 123 --web                 # Open in browser
glab issue view 123 --comments            # Include comments
```

### glab issue update

```bash
glab issue update 123 --title "New title"
glab issue update 123 --description "Updated description"
glab issue update 123 --add-label="in-progress"
glab issue update 123 --remove-label="todo"
glab issue update 123 --assignee="newuser"
glab issue update 123 --unassign           # Remove all assignees
glab issue update 123 --milestone=""       # Remove milestone
glab issue update 123 --lock               # Lock discussion
```

### glab issue note

```bash
glab issue note 123 -m "Comment text"
glab issue note 123                        # Opens editor for comment
```

## Merge Request Commands

### glab mr create

```bash
# Interactive creation
glab mr create

# Auto-fill from commits
glab mr create --fill
glab mr create --fill --fill-commit-body   # Include commit bodies

# Draft/WIP MR
glab mr create --draft
glab mr create --wip                       # Alias for --draft

# Full specification
glab mr create \
  -t "feat: Add user authentication" \
  -d "Implements OAuth2 login flow" \
  -b main \
  -s feature/auth \
  --label="feature,security" \
  --assignee="@me" \
  --reviewer="senior-dev" \
  --milestone="v2.0" \
  --squash-before-merge \
  --remove-source-branch

# From different repo
glab mr create -R group/other-repo

# Open in browser to continue
glab mr create --web
```

**Flags:**
- `-t, --title` - MR title
- `-d, --description` - MR description
- `-b, --target-branch` - Target branch (default: repo default)
- `-s, --source-branch` - Source branch (default: current branch)
- `-l, --label` - Labels (comma-separated)
- `-a, --assignee` - Assignees (comma-separated)
- `--reviewer` - Reviewers (comma-separated)
- `-m, --milestone` - Milestone
- `--draft` / `--wip` - Create as draft
- `--fill` - Auto-fill title/description from commits
- `--fill-commit-body` - Include commit bodies in description
- `--squash-before-merge` - Enable squash merge
- `--remove-source-branch` - Delete source branch on merge
- `--allow-collaboration` - Allow commits from maintainers
- `--create-source-branch` - Create source branch if missing
- `--related-issue` - Link to issue
- `--copy-issue-labels` - Copy labels from related issue
- `-y, --yes` - Skip confirmation
- `--web` - Open in browser

### glab mr for

Creates MR for a specific issue, auto-linking them:

```bash
glab mr for 123                            # Creates MR linked to issue #123
glab mr for 123 --draft
```

### glab mr list

```bash
# Basic listing
glab mr list                              # Open MRs
glab mr list --all                        # All states
glab mr list --merged                     # Only merged
glab mr list --closed                     # Only closed

# Filtering
glab mr list --assignee=@me               # Assigned to you
glab mr list --author=@me                 # Created by you
glab mr list --reviewer=@me               # Awaiting your review
glab mr list --draft                      # Draft MRs only
glab mr list --label="needs-review"
glab mr list --source-branch="feature/*"
glab mr list --target-branch="main"

# Output
glab mr list --output=json
```

### glab mr view

```bash
glab mr view 45                           # View in terminal
glab mr view 45 --web                     # Open in browser
glab mr view 45 --comments                # Include discussion
glab mr view                              # Current branch's MR
```

### glab mr checkout

```bash
glab mr checkout 45                       # Checkout MR branch
glab mr checkout 45 -b my-local-branch    # Custom local branch name
glab mr checkout 45 --detach              # Detached HEAD
```

### glab mr diff

```bash
glab mr diff 45                           # Show diff
glab mr diff                              # Current branch's MR
glab mr diff 45 --color=always | less -R  # Paged with colors
```

### glab mr update

```bash
# Modify MR properties
glab mr update 45 --title "New title"
glab mr update 45 --description "Updated"
glab mr update 45 --target-branch develop
glab mr update 45 --add-label="approved"
glab mr update 45 --remove-label="wip"
glab mr update 45 --draft=false           # Mark as ready
glab mr update 45 --draft=true            # Convert to draft
glab mr update 45 --assignee="newuser"
glab mr update 45 --reviewer="reviewer1,reviewer2"
glab mr update 45 --milestone="v2.0"
glab mr update 45 --squash-before-merge=true
glab mr update 45 --remove-source-branch=true
glab mr update 45 --lock-discussion       # Lock comments

# Interactive mode
glab mr update 45
glab mr update                            # Current branch's MR
```

### glab mr approve / revoke

```bash
glab mr approve 45
glab mr approve                           # Current branch's MR
glab mr revoke 45                         # Revoke approval
glab mr revoke
```

### glab mr merge

```bash
glab mr merge 45                          # Interactive merge
glab mr merge 45 --yes                    # Skip confirmation

# Merge strategies
glab mr merge 45 --squash                 # Squash commits
glab mr merge 45 --rebase                 # Rebase before merge
glab mr merge 45 --merge-commit-message "Merge feature X"

# Post-merge actions
glab mr merge 45 --remove-source-branch   # Delete branch after
glab mr merge 45 --when-pipeline-succeeds # Merge when CI passes

# Current branch's MR
glab mr merge
```

### glab mr rebase

```bash
glab mr rebase 45                         # Rebase MR onto target
glab mr rebase                            # Current branch's MR
```

### glab mr note

```bash
glab mr note 45 -m "Comment text"
glab mr note 45                           # Opens editor
glab mr note -m "LGTM"                    # Current branch's MR
```

### glab mr close / reopen / delete

```bash
glab mr close 45
glab mr reopen 45
glab mr delete 45
glab mr delete 45 --yes                   # Skip confirmation
```

## CI/CD Commands

### glab ci list

```bash
glab ci list                              # Recent pipelines
glab ci list --status=running
glab ci list --status=failed
glab ci list --ref=main                   # Specific branch
```

### glab ci view

```bash
glab ci view                              # Interactive TUI
glab ci view 12345                        # Specific pipeline
glab ci view --web                        # Open in browser
```

### glab ci run

```bash
glab ci run                               # Current branch
glab ci run -b main                       # Specific branch
glab ci run --variables KEY1=val1,KEY2=val2
```

### glab ci retry

```bash
glab ci retry                             # Retry latest failed
glab ci retry 12345                       # Retry specific pipeline
```

### glab ci trace

```bash
glab ci trace                             # Interactive job selector
glab ci trace 67890                       # Specific job logs
```

### glab ci status

```bash
glab ci status                            # Current pipeline status
glab ci status -b main                    # Specific branch
glab ci status --live                     # Live updates
```

### glab ci lint

```bash
glab ci lint                              # Validate .gitlab-ci.yml
glab ci lint path/to/file.yml             # Custom file
```

## Repository Commands

### glab repo clone

```bash
glab repo clone owner/repo
glab repo clone owner/repo target-dir
glab repo clone -g groupname              # Clone all repos in group
```

### glab repo view

```bash
glab repo view                            # Current repo
glab repo view owner/repo
glab repo view --web                      # Open in browser
```

### glab repo fork

```bash
glab repo fork owner/repo
glab repo fork owner/repo --clone         # Fork and clone
```

## Configuration

### glab config

```bash
# View config
glab config list
glab config get editor

# Set config
glab config set editor vim
glab config set browser firefox
glab config set git_protocol ssh
glab config set check_update false

# Per-host config
glab config set token xxxx --host gitlab.example.com
```

### Aliases

```bash
# Create alias
glab alias set co 'mr checkout'
glab alias set review 'mr list --reviewer=@me'

# List aliases
glab alias list

# Delete alias
glab alias delete co
```

## Tips & Patterns

### Complete WIP Branch Workflow

```bash
# 1. Create feature branch from issue
git checkout -b feature/issue-123-add-auth

# 2. Make changes and commit
git add .
git commit -m "feat: add OAuth2 authentication

Implements login flow with:
- Google OAuth2 provider
- Session management
- Token refresh

Closes #123"

# 3. Push and create draft MR
git push -u origin feature/issue-123-add-auth
glab mr create --draft --fill --related-issue=123

# 4. Continue working, push updates
git add .
git commit -m "fix: handle token expiration"
git push

# 5. Mark ready for review
glab mr update --draft=false --reviewer="senior-dev"

# 6. After approval, merge
glab mr merge --squash --remove-source-branch
```

### Quick Review Workflow

```bash
# 1. See pending reviews
glab mr list --reviewer=@me

# 2. Checkout and test
glab mr checkout 45

# 3. Review diff
glab mr diff 45

# 4. Add feedback or approve
glab mr note 45 -m "Looks good, minor nit on line 42"
glab mr approve 45
```

### Batch Operations

```bash
# Close all MRs with specific label
glab mr list --label="stale" --json=iid | jq -r '.[].iid' | xargs -I {} glab mr close {}

# Approve multiple MRs
for mr in 10 11 12; do glab mr approve $mr; done
```
