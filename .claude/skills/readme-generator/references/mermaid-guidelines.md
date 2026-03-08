# Mermaid Diagram Guidelines

Mermaid diagrams are one of the most valuable parts of a good README. They make complex systems, data flows, and processes immediately understandable in a way that paragraphs of text cannot. Use them generously — if something involves flow, sequence, or relationships between components, a mermaid diagram is almost always better than a written description.

## When to Use Mermaid Diagrams

Include a diagram for any of these situations that apply to the project:

- **System architecture** — how components connect (almost every README should have at least one)
- **Data flow / pipelines** — how data moves through the system from source to destination
- **Request/response sequences** — what happens when a user takes an action (`sequenceDiagram`)
- **Decision trees / workflows** — multi-step processes with branches (e.g. "Adding a new X")
- **Module dependencies** — how internal modules import from each other
- **CI/CD pipelines** — build/test/deploy stages
- **State machines** — entities with multiple states and transitions
- **UI layout** — dashboard/page structure showing how sections relate

A typical comprehensive README should have **3-6 mermaid diagrams**. Complex projects (data pipelines, multi-service systems) might have **6-10+**. Don't hold back — if a diagram would help someone understand something, include it.

## Best Practices

- **Keep individual diagrams focused.** Each diagram should explain one thing well. If a diagram has 15+ nodes, consider splitting it.
- **Use subgraphs** to group related components: `subgraph "Database Layer"`
- **Label edges** to explain relationships: `A -->|"raw data"| B` is much more useful than `A --> B`
- **Use descriptive node labels**: `SF["Snowflake Data Warehouse"]` not just `SF`
- **Choose the right diagram type:**
  - `graph TD` / `graph LR` — architecture, data flow, dependencies
  - `sequenceDiagram` — request/response flows, "what happens when..."
  - `flowchart TD` — decision trees, processes with branches

## Choosing Diagrams by Project Type

### Data pipeline project — aim for 4-6 diagrams:

1. Architecture diagram — overall system with data sources, processing, and outputs
2. Data flow diagram — how data moves from raw sources through transformations to final output
3. Sequence diagram — what happens when a pipeline run is triggered
4. Module dependency graph — how source code modules relate to each other
5. Data validation / quality checks flow
6. Scheduling / orchestration diagram

### Web application — aim for 3-5 diagrams:

1. Architecture diagram — frontend, backend, database, external services
2. Request flow — what happens when a user performs a key action
3. CI/CD diagram — build and deployment pipeline
4. Dashboard/UI layout — how sections of the interface relate

### CLI tool — aim for 2-4 diagrams:

1. Architecture diagram — how the CLI interacts with external systems
2. Command flow — what happens when key commands are run
3. Configuration resolution — how config is loaded from files, env vars, and defaults
