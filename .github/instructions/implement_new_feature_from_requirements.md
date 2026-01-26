# Implementing Features from Requirements

When asked to implement a feature from a requirements document:


## Step 1: Read Requirements

1. Read the entire requirements document from `docs/requirements/`
2. Identify ambiguities, missing details, or conflicting constraints
3. List all external dependencies (APIs, services, models)


## Step 2: Clarify Before Coding

**STOP. Do not write implementation code yet.**

1. Present questions to the user covering:
   - Unclear acceptance criteria
   - Edge cases not addressed
   - Integration points with existing code
   - Suggestions for improving the functionality
2. Wait for user responses
3. Update the requirements document with clarifications inline
4. Create implementation plan: `docs/requirements/<feature>_implementation_plan.md`

### Implementation Plan Format

```markdown
# <Feature> Implementation Plan

## Summary
One paragraph describing what will be built.

## Files to Create
- path/to/new_file.py: purpose

## Files to Modify
- path/to/existing.py: what changes

## Database Changes
- New models or fields
- Migration requirements

## External API Calls
- Endpoint, method, expected response

## Task Sequence
1. Step with acceptance criteria
2. Step with acceptance criteria

## Test Plan
- Unit tests: list scenarios
- Integration tests: list scenarios

## Diagrams
- For complex features: Create Mermaid diagram in `docs/diagrams/`
- If modifying existing flows: List diagrams to update

## Open Questions
- Any remaining uncertainties```


## Step 3: Push a simple PR with just the implementation plan

1. Push a PR with the implementation plan
2. Wait for feedback from the user


## Step 4: Write Code

1. Follow the implementation plan sequentially
2. After each task, run: `ruff check . && pyright`
3. Write tests alongside implementation
4. If blocked or uncertain, ask the user before proceeding


## Step 5: Completion Checklist

Before marking feature complete:

- [ ] All implementation plan tasks done
- [ ] Tests pass: `pytest`
- [ ] Linting passes: `ruff check .`
- [ ] Type checking passes: `pyright`
- [ ] Migrations generated if needed
- [ ] Requirements doc: updated with final state
- [ ] Diagrams created/updated (if applicable)
  - Complex features: Add Mermaid diagram to `docs/diagrams/`
  - Existing flows modified: Update relevant diagrams
