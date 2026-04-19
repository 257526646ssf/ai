# .codex/skills/feature-impl-checklist/SKILL.md

---
name: feature-impl-checklist
description: Use this skill when implementing a new feature for the AI testing assistant. Ensures planning, scoped changes, validation, and safe AI integration.
---

## Instructions
When asked to implement a feature:

1. Read the relevant files first
2. Summarize the implementation plan
3. Reuse existing patterns and modules
4. Keep model calls behind the adapter layer
5. Add or update tests for new logic
6. Verify loading / empty / error / retry states if UI is involved
7. Verify types, validation, and error handling if API is involved
8. Report:
   - changed files
   - implementation summary
   - validation results
   - remaining risks