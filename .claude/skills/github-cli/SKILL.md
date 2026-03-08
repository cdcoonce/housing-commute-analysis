```skill
---
name: github-cli
description: >
  GitHub CLI (gh) integration for managing issues, pull requests, branches,
  commits, and code reviews directly from the terminal. Use when Claude needs to
  create, list, view, or update GitHub issues; create draft branches and
  pull requests; make commits and push changes; review pull request diffs and
  changes; approve or merge PRs; manage GitHub Actions workflows; or work with
  GitHub repositories without switching to a browser. Requires gh CLI installed
  and authenticated.
---
```

# GitHub CLI (gh) Skill

Use the `gh` CLI to interact with GitHub repositories, issues, pull requests, and GitHub Actions workflows from the terminal.

## Prerequisites

Verify gh is installed and authenticated:

```bash
gh --version
gh auth status
```

If not authenticated, run `gh auth login` and follow prompts.

## Core Workflows

### Issue Management

```bash
# List issues
gh issue list                             # Open issues in current repo
gh issue list --state all                 # All issues including closed
gh issue list --assignee @me              # Issues assigned to you
gh issue list --label "bug"               # Filter by label

# Create issue
gh issue create -t "Title" -b "Description"
gh issue create -t "Title" --label "bug,priority:high" --milestone "milestone-1"
gh issue create                           # Interactive mode

# View/update issue
gh issue view 123                         # View issue details
gh issue view 123 --web                   # Open in browser
gh issue edit 123 --add-label "in-progress"
gh issue close 123
gh issue reopen 123

# Add comments
gh issue comment 123 -b "Working on this now"
```

### Branch & Commit Workflow

```bash
# Create feature/fix branch
git checkout -b feature/my-feature
git checkout -b fix/issue-123
git checkout -b draft/wip-experiment

# Stage and commit changes
git add .
git commit -m "feat: add new feature"
git commit -m "fix: resolve issue #123"

# Push branch to remote
git push -u origin feature/my-feature
```

### Pull Request Management

```bash
# Create PR (multiple methods)
gh pr create                              # Interactive mode
gh pr create --fill                       # Auto-fill from commits
gh pr create --draft                      # Create as draft
gh pr create --draft --fill               # Draft with auto-fill
gh pr create -t "Title" -b "Description" -B main
gh pr create --label "review-needed" --assignee @me

# List PRs
gh pr list                                # Open PRs
gh pr list --assignee @me                 # Your PRs
gh pr list --search "review-requested:@me"  # PRs requesting your review
gh pr list --draft                        # Draft PRs only

# View PR details
gh pr view 45                             # View PR in terminal
gh pr view 45 --web                       # Open in browser
```

### Code Review Workflow

```bash
# Checkout PR locally for testing
gh pr checkout 45                         # Checkout PR branch locally

# Review changes
gh pr diff 45                             # View PR diff
gh pr diff                                # Diff for current branch's PR

# Add review comments
gh pr comment 45 -b "LGTM, minor suggestion on line 42"
gh pr comment -b "Please add tests"       # Comment on current branch's PR

# Submit a formal review
gh pr review 45 --approve
gh pr review 45 --request-changes -b "Please fix the error handling"
gh pr review 45 --comment -b "Looks good overall, a few suggestions"

# Merge
gh pr merge 45                            # Interactive merge
gh pr merge 45 --squash                   # Squash merge
gh pr merge 45 --rebase                   # Rebase merge
gh pr merge 45 --merge                    # Standard merge commit
gh pr merge 45 --auto                     # Auto-merge when checks pass
```

### Update Existing PR

```bash
gh pr edit 45 --title "New title"
gh pr edit 45 --body "Updated description"
gh pr edit 45 --base develop
gh pr edit 45 --add-label "ready-for-review"
gh pr ready 45                            # Mark ready (remove draft)
```

### GitHub Actions Workflow Management

```bash
# List workflow runs
gh run list                               # Recent workflow runs
gh run list --workflow=ci.yml             # Specific workflow
gh run list --status=failure              # Failed runs only

# View workflow run details
gh run view                               # Interactive run selector
gh run view 12345                         # Specific run
gh run view 12345 --web                   # Open in browser

# Trigger workflow
gh workflow run ci.yml                    # Run on default branch
gh workflow run ci.yml --ref feature/x    # Run on specific branch
gh workflow run ci.yml -f key=value       # With input parameters

# Re-run failed jobs
gh run rerun 12345                        # Re-run all jobs
gh run rerun 12345 --failed               # Re-run only failed jobs

# View job logs
gh run view 12345 --log                   # Full log output
gh run view 12345 --log-failed            # Only failed job logs

# Watch a run in progress
gh run watch                              # Watch current run
gh run watch 12345                        # Watch specific run
```

## Common Flag Reference

| Flag                    | Description                    |
| ----------------------- | ------------------------------ |
| `-R, --repo OWNER/REPO` | Target different repository    |
| `-B, --base`            | Base branch for PR             |
| `-H, --head`            | Head branch for PR             |
| `-t, --title`           | Title for issue/PR             |
| `-b, --body`            | Body/description for issue/PR  |
| `-l, --label`           | Labels (comma-separated)       |
| `-a, --assignee`        | Assignee username              |
| `-m, --milestone`       | Milestone name                 |
| `--draft`               | Create as draft PR             |
| `--fill`                | Auto-fill from commit messages |
| `--web`                 | Open in browser                |
| `-y, --yes`             | Skip confirmation prompts      |

## Environment Variables

```bash
export GH_TOKEN="ghp_xxxx"               # Personal access token
export GH_HOST="github.example.com"      # GitHub Enterprise instance
export GH_REPO="owner/repo"              # Default repository
```

## Tips & Gotchas

### Multi-line Descriptions with Markdown

When creating issues or PRs with long descriptions containing markdown (code blocks, backticks), avoid heredocs which can fail due to shell interpretation. Instead:

```bash
# Step 1: Write description to a temp file (outside bash)
# Step 2: Create from the temp file
gh issue create -t "Title" -b "$(cat temp_description.txt)"
# Step 3: Clean up
rm temp_description.txt
```

This avoids issues with:

- Backticks in code blocks conflicting with command substitution
- Special characters being interpreted by the shell
- Heredoc delimiter conflicts

### Sourcing Description from Existing Files

To create an issue or PR from a markdown plan file:

```bash
# Use body-file flag for clean file-based descriptions
gh issue create -t "Title" --body-file docs/plans/my-plan.md
gh pr create -t "Title" --body-file docs/plans/my-plan.md
```

## Detailed Reference

For comprehensive command options and examples, see [references/commands.md](references/commands.md).
