# Fix Approval Workflow Reference

This document describes the workflow for reviewing and applying suggested fixes.

## Overview

The code review process follows these steps:

1. **Analyze** - Run linters and Claude analysis on code
2. **Report** - Generate report with issues and suggested fixes
3. **Review** - User reviews the report
4. **Approve** - User selects which fixes to apply
5. **Apply** - Implement approved fixes

## Approval Modes

The user can choose how to approve fixes:

### 1. All at Once

Review the complete report, then approve or reject all fixes together.

```
User: "Apply all the suggested fixes"
User: "Apply all auto-fixable issues"
User: "Don't apply any fixes, I'll handle them manually"
```

### 2. By Category

Approve fixes grouped by issue category.

```
User: "Apply all PEP8 fixes"
User: "Fix all the unused imports"
User: "Apply docstring fixes but skip type hint ones"
```

Categories:
- `pep8` - Style violations
- `type_hint` - Type annotation issues
- `docstring` - Documentation issues
- `unused_code` - Dead code
- `complexity` - Complexity issues
- `import` - Import organization
- `markdown` - Markdown formatting
- `mermaid` - Diagram syntax

### 3. By Severity

Approve fixes by severity level.

```
User: "Fix all errors first"
User: "Apply warning-level fixes only"
User: "Skip the info-level suggestions"
```

### 4. By File

Approve fixes for specific files.

```
User: "Apply fixes to main.py only"
User: "Fix everything except test files"
```

### 5. Individual

Review and approve each fix one at a time.

```
User: "Show me each fix and let me decide"
User: "Walk me through the fixes one by one"
```

## Fix Application Process

### For Auto-Fixable Issues

1. Claude presents the original code and suggested fix
2. User approves the change
3. Claude applies the fix using `str_replace` or file operations
4. Claude confirms the change was applied

### For Manual Fixes

1. Claude explains what needs to change and why
2. Claude may provide code suggestions
3. User implements the fix manually
4. User can ask Claude to verify the fix

## Verification

After applying fixes:

1. Re-run analysis to confirm issues are resolved
2. Report any new issues introduced
3. Provide updated statistics

## Example Workflow

```
Claude: I found 15 issues in your code:
        - 3 errors (must fix)
        - 8 warnings (should fix)
        - 4 info (consider fixing)
        
        12 of these are auto-fixable. How would you like to proceed?
        
        Options:
        1. Apply all auto-fixable issues
        2. Review by category
        3. Review individually
        4. Show me the report first

User: Let's fix all the errors first, then review the warnings.

Claude: Applying 3 error fixes...
        ✓ Fixed undefined variable in utils.py:42
        ✓ Fixed syntax error in parser.py:15
        ✓ Fixed security issue in auth.py:88
        
        Now for the 8 warnings. Would you like to:
        1. Apply all 8 warning fixes
        2. Review by category (3 unused imports, 3 PEP8, 2 type hints)
        3. Review individually
```

## Safety Considerations

- Always show diff before applying changes
- Back up files before bulk operations
- Verify changes don't break functionality
- Re-run tests after applying fixes
- Some fixes may have unintended consequences

## Declining Fixes

The user can always decline fixes:

```
User: "Skip this one"
User: "Don't fix the type hints, they're intentionally missing"
User: "I disagree with this suggestion"
```

Claude should respect user decisions and not repeatedly suggest declined fixes.
