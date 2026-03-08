# Markdown Quality Checks Reference

This document details the Markdown documentation quality checks performed by the code-review skill.

## Heading Structure

### MD001 - Heading Level Increment

Headings should only increment by one level at a time.

```markdown
# Title

### Skipped h2 <!-- Issue: skipped from h1 to h3 -->
```

**Severity:** WARNING  
**Auto-fixable:** Yes

### MD025 - Single Top-Level Heading

Documents should have only one h1 heading.

```markdown
# First Title

# Second Title <!-- Issue: duplicate h1 -->
```

**Severity:** WARNING  
**Auto-fixable:** Yes (change to h2)

### MD041 - First Line Heading

The first non-blank line should be a top-level heading.

```markdown
## Not an h1 <!-- Issue: should start with h1 -->
```

**Severity:** WARNING  
**Auto-fixable:** Yes

### MD024 - Duplicate Headings

Multiple headings with the same content should be avoided for clarity.

**Severity:** INFO  
**Auto-fixable:** No

## Links

### MD042 - Empty Link URL

Links should have non-empty URLs.

```markdown
[Click here]() <!-- Issue: empty URL -->
```

**Severity:** ERROR  
**Auto-fixable:** No

### MD045 - Empty Link/Image Text

Links and images should have descriptive text.

```markdown
[](https://example.com) <!-- Issue: empty text -->
![](image.png) <!-- Issue: missing alt text -->
```

**Severity:** WARNING  
**Auto-fixable:** No

### MD052 - Broken Links

Relative links should point to existing files.

```markdown
[Docs](nonexistent.md) <!-- Issue: file not found -->
```

**Severity:** ERROR  
**Auto-fixable:** No

### MD053 - Broken Images

Image paths should point to existing files.

```markdown
![Logo](missing-logo.png) <!-- Issue: file not found -->
```

**Severity:** ERROR  
**Auto-fixable:** No

## Formatting

### MD009 - Trailing Whitespace

Lines should not have trailing whitespace (except for intentional line breaks).

**Severity:** INFO  
**Auto-fixable:** Yes

### MD012 - Multiple Blank Lines

No more than one consecutive blank line.

```markdown
Some text

<!-- Issue: multiple blank lines -->

More text
```

**Severity:** INFO  
**Auto-fixable:** Yes

### MD022 - Blank Lines Around Headings

Headings should be surrounded by blank lines.

```markdown
# Title

No blank line after heading <!-- Issue -->
```

**Severity:** INFO  
**Auto-fixable:** No

## Code Blocks

### MD040 - Fenced Code Block Language

Code blocks should specify a language for syntax highlighting.

````markdown
```
print("hello")  <!-- Issue: no language specified -->
```
````

**Severity:** INFO  
**Auto-fixable:** No

## Accessibility

### Image Alt Text

Images should include descriptive alt text for screen readers and accessibility compliance.

```markdown
![Descriptive alt text](image.png) <!-- Good -->
![](image.png) <!-- Bad: missing alt text -->
```

**Severity:** WARNING  
**Auto-fixable:** No

## Best Practices

When writing Markdown documentation:

1. Start with a single h1 heading as the document title
2. Use heading levels sequentially (h1 → h2 → h3)
3. Include alt text for all images
4. Use descriptive link text (avoid "click here")
5. Specify language for code blocks
6. Keep consistent spacing around headings

## Encoding Corruption (MD050)

UTF-8 encoding corruption occurs when text is saved or transmitted with incorrect encoding, causing characters to appear garbled.

### Common Corruption Patterns

| Corrupted    | Correct | Description         |
| ------------ | ------- | ------------------- |
| Ã—           | ×       | Multiplication sign |
| Ã·           | ÷       | Division sign       |
| â€"          | —       | Em dash             |
| â€"          | –       | En dash             |
| â€¢          | •       | Bullet point        |
| âœ"          | ✓       | Checkmark           |
| â†           | ←       | Left arrow          |
| â†'          | →       | Right arrow         |
| Â©          | ©      | Copyright           |
| Â®          | ®      | Registered          |
| â„¢          | ™      | Trademark           |
| â"Œâ"€â"€â"˜ | ┌──┘    | Box drawing         |

### Example

**Corrupted:**

```markdown
Revenue = Generation Ã— Price
```

**Fixed:**

```markdown
Revenue = Generation × Price
```

**Severity:** ERROR  
**Auto-fixable:** Yes

### How It Happens

This typically occurs when:

1. A UTF-8 file is opened as Latin-1/Windows-1252
2. Text is copy-pasted between systems with different encodings
3. Database or API doesn't properly handle UTF-8

### Prevention

- Always save files with UTF-8 encoding
- Set proper encoding headers in web applications
- Use UTF-8 throughout your toolchain

## Mermaid Diagram Validation

### MD060 - Mermaid Syntax Errors

Mermaid diagrams embedded in code blocks should have valid syntax.

**Severity:** ERROR
**Auto-fixable:** No

### MD061 - Parentheses in Mermaid Node Labels

Node labels containing unescaped parentheses cause parse errors because Mermaid interprets them as special shape syntax.

**Bad:**

````markdown
```mermaid
flowchart TD
    A[Function (deprecated)]
```
````

````

**Good:**
```markdown
```mermaid
flowchart TD
    A[Function - deprecated]
````

````

Alternative: Use quotes to escape special characters:
```markdown
```mermaid
flowchart TD
    A["Function (deprecated)"]
````

```

**Severity:** ERROR
**Auto-fixable:** Yes (replace parentheses with dashes)

### Common Mermaid Parse Errors

| Symptom | Cause | Fix |
|---------|-------|-----|
| `Expecting 'SQE', 'PE'...` | Unescaped parentheses in node label | Replace `(text)` with `- text` or `["text (with parens)"]` |
| `Parse error on line X` | Invalid syntax | Check node definitions and arrow syntax |
| `Undefined` node reference | Typo in node ID | Ensure node IDs match exactly |
```
