---
name: gitlab-cli
description: >
  GitLab CLI (glab) integration for managing issues, merge requests, branches,
  commits, and code reviews directly from the terminal. Use when Claude needs to
  create, list, view, or update GitLab issues; create WIP/draft branches and
  merge requests; make commits and push changes; review merge request diffs and
  changes; approve or merge MRs; manage CI/CD pipelines; or work with GitLab
  repositories without switching to a browser. Requires glab CLI installed and
  authenticated.
---

# GitLab CLI (glab) Skill

Use the `glab` CLI to interact with GitLab repositories, issues, merge requests, and CI/CD pipelines from the terminal.

## Prerequisites

Verify glab is installed and authenticated:

```bash
glab --version
glab auth status
```

If not authenticated, run `glab auth login` and follow prompts.

## Core Workflows

### Issue Management

```bash
# List issues
glab issue list                           # Open issues in current repo
glab issue list --all                     # All issues including closed
glab issue list --assignee=@me            # Issues assigned to you
glab issue list --label="bug"             # Filter by label

# Create issue
glab issue create -t "Title" -d "Description"
glab issue create -t "Title" --label="bug,priority::high" -m "milestone-1"
glab issue create                         # Interactive mode

# View/update issue
glab issue view 123                       # View issue details
glab issue view 123 --web                 # Open in browser
glab issue update 123 --label="in-progress"
glab issue close 123
glab issue reopen 123

# Add notes/comments
glab issue note 123 -m "Working on this now"
```

### Branch & Commit Workflow

```bash
# Create WIP/feature branch
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

### Merge Request Management

```bash
# Create MR (multiple methods)
glab mr create                            # Interactive mode
glab mr create --fill                     # Auto-fill from commits
glab mr create --draft                    # Create as draft/WIP
glab mr create --draft --fill             # Draft with auto-fill
glab mr create -t "Title" -d "Description" -b main
glab mr create --label="review-needed" --assignee=@me

# Create MR from issue (links MR to issue)
glab mr for 123                           # Creates MR for issue #123

# List MRs
glab mr list                              # Open MRs
glab mr list --assignee=@me               # Your MRs
glab mr list --reviewer=@me               # MRs requesting your review
glab mr list --draft                      # Draft MRs only

# View MR details
glab mr view 45                           # View MR in terminal
glab mr view 45 --web                     # Open in browser
```

### Code Review Workflow

```bash
# Checkout MR locally for testing
glab mr checkout 45                       # Checkout MR branch locally

# Review changes
glab mr diff 45                           # View MR diff
glab mr diff                              # Diff for current branch's MR

# Add review comments
glab mr note 45 -m "LGTM, minor suggestion on line 42"
glab mr note -m "Please add tests"        # Note on current branch's MR

# Approve and merge
glab mr approve 45
glab mr merge 45                          # Interactive merge
glab mr merge 45 --squash                 # Squash merge
glab mr merge 45 --rebase                 # Rebase merge
glab mr merge 45 --yes                    # Skip confirmation

# Request changes or revoke approval
glab mr revoke 45                         # Revoke your approval
```

### Update Existing MR

```bash
glab mr update 45 --title "New title"
glab mr update 45 --description "Updated description"
glab mr update 45 --target-branch develop
glab mr update 45 --label "ready-for-review"
glab mr update 45 --draft=false           # Mark ready (remove draft)
glab mr update                            # Interactive update
```

### CI/CD Pipeline Management

```bash
# View pipelines
glab ci list                              # List recent pipelines
glab ci view                              # Interactive pipeline viewer
glab ci status                            # Current pipeline status

# Run/retry pipelines
glab ci run                               # Trigger pipeline on current branch
glab ci run -b main                       # Trigger on specific branch
glab ci retry                             # Retry failed pipeline

# View job logs
glab ci trace                             # Interactive job log viewer
glab ci trace 12345                       # Specific job logs

# Lint CI config
glab ci lint                              # Validate .gitlab-ci.yml
```

## Common Flag Reference

| Flag                    | Description                    |
| ----------------------- | ------------------------------ |
| `-R, --repo OWNER/REPO` | Target different repository    |
| `-b, --target-branch`   | Target branch for MR           |
| `-s, --source-branch`   | Source branch for MR           |
| `-t, --title`           | Title for issue/MR             |
| `-d, --description`     | Description for issue/MR       |
| `-l, --label`           | Labels (comma-separated)       |
| `-a, --assignee`        | Assignee username              |
| `-m, --milestone`       | Milestone name                 |
| `--draft`               | Create as draft MR             |
| `--fill`                | Auto-fill from commit messages |
| `--web`                 | Open in browser                |
| `-y, --yes`             | Skip confirmation prompts      |

## Environment Variables

```bash
export GITLAB_TOKEN="glpat-xxxx"          # Auth token
export GITLAB_HOST="https://gitlab.example.com"  # Self-hosted instance
```

## Tips & Gotchas

### Multi-line Descriptions with Markdown

When updating issues or MRs with long descriptions containing markdown (code blocks, backticks), avoid heredocs which can fail due to shell interpretation. Instead:

```bash
# Step 1: Write description to a temp file (outside bash)
# Step 2: Update from the temp file
glab issue update 123 --description "$(cat temp_description.txt)"
# Step 3: Clean up
rm temp_description.txt
```

This avoids issues with:

- Backticks in code blocks conflicting with command substitution
- Special characters being interpreted by the shell
- Heredoc delimiter conflicts

### Sourcing Description from Existing Files

To update an issue from a markdown plan file:

```bash
# Skip header lines (e.g., title, metadata) and use rest as description
cat docs/plans/my-plan.md | tail -n +7 > temp_desc.txt
glab issue update 123 --description "$(cat temp_desc.txt)"
rm temp_desc.txt
```

## Detailed Reference

For comprehensive command options and examples, see [references/commands.md](references/commands.md).
