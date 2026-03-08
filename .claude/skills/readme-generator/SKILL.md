---
name: readme-generator
description: Generate comprehensive, high-quality README.md files for code repositories. Use this skill whenever the user asks to create, write, generate, update, or improve a README for any project or repository. Also trigger when the user says things like "document this project", "write docs for this repo", "this repo needs a README", "help me onboard developers to this codebase", or asks for project documentation in markdown. Even if the user just says "README" or "readme" in the context of a codebase, use this skill.
---

# README Generator

Create polished, comprehensive README.md files for internal/company code repositories by analyzing the actual codebase and asking targeted clarifying questions.

## Why this skill exists

A good README is the front door to a codebase. For internal projects especially, a missing or thin README means every new team member burns hours figuring out what a project does, how to run it, and where to look. This skill automates the heavy lifting — it reads the code, infers what it can, asks about what it can't, and produces a README that gets developers productive fast.

## Workflow

### Step 1: Analyze the codebase

Before asking the user anything, execute a structured four-phase analysis to gather as much context as possible. This reduces the burden on the user — they should only need to fill gaps, not describe things you can already see.

Tag every fact with a confidence level: `[confirmed]` (read from source), `[inferred-high]` (strong evidence), `[inferred-low]` (partial evidence), or `[unknown]`. Low-confidence and unknown findings become clarifying questions in Step 2.

See [references/analysis-phases.md](references/analysis-phases.md) for detailed tool actions, grep patterns, extraction checklists, and record templates.

**Phase 1 — Project Metadata Scan:** Glob for package manager files (`pyproject.toml`, `package.json`, etc.), env templates, Dockerfiles, CI/CD configs, and toolchain files. Read each and extract: project name/version, language, dependencies (categorized with purposes), scripts/commands, environment variables (required vs optional), CI stages, license.

**Phase 2 — Architecture Scan:** Glob for all source files to map directory structure. Grep for entry point markers (`if __name__`, `main()`, etc.) and read each entry point. Build the import graph by grepping for import statements across all source files — classify modules as core (high in-degree), leaf, or orchestrator. Identify the architecture pattern (pipeline, MVC, layered, microservices, event-driven, CLI, monolith) using the indicator checklist. Grep for config-loading patterns to find runtime config files.

**Phase 3 — Deep Module Analysis:** Read each significant source file (prioritized: core → entry point → largest → rest). For each, extract: purpose (one sentence), key exports with signatures, design notes (non-obvious decisions, edge cases, conventions), and internal dependencies. Trace the primary workflow end-to-end through the import graph, labeling what data types flow between modules. For codebases with 8+ source files, dispatch parallel subagents grouped by dependency cluster.

**Phase 4 — Supporting Infrastructure Scan:** Glob for test files and fixtures. Read first 30-50 lines of each test file to build a test-to-module mapping. Grep for custom exception classes and `raise` statements to map the error hierarchy. Scan templates, assets, and existing docs. Extract common error scenarios for the Troubleshooting table.

### Step 2: Ask clarifying questions

After analysis, ask the user about things you couldn't confidently infer. Keep it focused — don't ask about things you already know. Common gaps include:

- **Project purpose**: What problem does this solve? Who uses it? (if not obvious from code)
- **Setup gotchas**: Are there non-obvious prerequisites, VPN requirements, internal package registries, or database setup steps?
- **Key workflows**: What are the 2-3 things a developer does most often with this project?
- **Deployment**: How/where is this deployed? (if not clear from CI/CD configs)
- **Team conventions**: Any naming conventions, branching strategies, or patterns to call out?
- **Contact info**: Who owns/maintains this project? (name + email for the Contact section)

Present your questions concisely. If the codebase is straightforward and you're confident in your analysis, you may only need 1-2 questions — or even none. Use your judgment.

### Step 3: Generate the README.md

Write the README using the structure and guidelines below.

## README Structure

Use this as your template. Include all sections, but scale depth to match the project's complexity. Use `---` horizontal rules between every major section for visual breathing room.

````markdown
# Project Name

![Language](https://img.shields.io/badge/...) ![Framework](https://img.shields.io/badge/...) ![Tool](https://img.shields.io/badge/...)

Brief, clear description. Use **bold** to highlight the key technology or product type.

---

## Table of Contents

Generate a thorough, nested table of contents that includes ALL ## and ### headings. Indent sub-sections under their parents so readers can see the full structure at a glance. This is especially important for longer READMEs — the TOC serves as both a navigation tool and an outline of the entire document.

Example of the expected depth:

- [Overview](#overview)
- [Architecture](#architecture)
  - [High-Level Architecture](#high-level-architecture)
  - [Folder Structure](#folder-structure)
  - [Module Dependency Graph](#module-dependency-graph)
- [Getting Started](#getting-started)
  - [Prerequisites](#prerequisites)
  - [Installation](#installation)
  - [Running Tests](#running-tests)
- [Environment Variables](#environment-variables)
- [Usage](#usage)
  - [Example: Primary Use Case](#example-primary-use-case)
  - [Example: Secondary Use Case](#example-secondary-use-case)
- [API Reference](#api-reference)
  - [Resource A](#resource-a)
  - [Resource B](#resource-b)
- [Troubleshooting](#troubleshooting)
- [Contact](#contact)
- [License](#license)

Every ### heading in the document should appear as an indented entry under its parent ## heading. Don't skip sub-sections — the whole point of a thorough TOC is that readers can jump directly to any part of the document.

---

## Overview

Expand on the description. Bold key terms. Use numbered lists for multi-step processes.

---

## Architecture

### High-Level Architecture

```mermaid
graph TD
    ...
```
````

### Folder Structure

```
project-root/
├── src/           # Brief annotation
├── tests/         # Brief annotation
└── ...
```

### [Data Flow / Pipeline / Module Dependencies — additional diagrams]

```mermaid
...
```

---

## Getting Started

### Prerequisites

### Installation

### Running Tests

---

## Environment Variables

| Variable | Required | Description                  |
| -------- | -------- | ---------------------------- |
| `DB_URL` | Yes      | PostgreSQL connection string |

---

## Usage

Real code examples for the 2-3 most common operations.

---

## API Reference <!-- if applicable -->

---

## Troubleshooting

| Symptom         | Likely Cause | Fix           |
| --------------- | ------------ | ------------- |
| `error message` | What's wrong | How to fix it |

---

## Contact

For questions or support, contact:

- **Name** — email@company.com

---

## License

**Internal Use Only – Company Name**
Proprietary software. © [Year] [Company]. All rights reserved.

```

## Shields.io Badges

Always include shields.io badges directly after the `# Title` heading (3-6 badges covering language, framework, key library, package manager, database, infrastructure). See [references/badge-reference.md](references/badge-reference.md) for format, examples, and color suggestions by category.

## Mermaid Diagram Guidelines

Use mermaid diagrams generously — they make architecture, data flows, and processes immediately understandable. A typical README should have **3-6 diagrams**; complex projects (data pipelines, multi-service systems) might have **6-10+**. See [references/mermaid-guidelines.md](references/mermaid-guidelines.md) for when to use each diagram type, best practices, and project-type-specific recommendations.

## Writing Guidelines

- **Be specific over generic.** "Run `npm run dev`" beats "Start the development server." Include actual commands, file paths, and variable names.
- **Write for the new team member.** Assume general engineering skills but zero project context.
- **Bold key terms and product names** on first mention and in overviews. This helps readers scan.
- **Use numbered lists for sequential processes.** "1. **Extracts** data from X. 2. **Transforms** it. 3. **Loads** into Y." — bold the verb.
- **Code examples should be runnable.** Copy from the actual codebase when possible.
- **Environment variable tables are non-negotiable.** List every single one.
- **Troubleshooting in table format** (Symptom | Likely Cause | Fix) — scannable and consistent.
- **Folder structure annotations should be brief.** One short phrase per directory.
- **Always include a Contact section.** Ask the user who maintains the project. Format: `**Name** — email@company.com`.
- **Use `---` horizontal rules** between all major sections for visual structure.

## Output

Save the README as `README.md` in the root of the repository (or the current working directory if no repo root is identifiable). If a README.md already exists, confirm with the user before overwriting — they may want to keep parts of it.
```
