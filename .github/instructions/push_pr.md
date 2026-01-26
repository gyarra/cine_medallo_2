# Pull Request Workflow

When asked to create a PR or push changes:

## 1. Create Feature Branch

```bash
git checkout -b <descriptive-branch-name>
```

## 2. Run All Checks

```bash
source .venv/bin/activate
ruff check .
pyright
python manage.py check
python manage.py makemigrations --check --dry-run
pytest
```

## 3. Code Review

1. Read code_review.md
2. Do a code review of all changes and fix any issues
3. Run all checks again (step 2)


## 4. Documentation

- Is there any documentation that should be update?
- Are there any lessons learned or things to remember that should be saved to copilot-instructions?
  - Do not save current state
  - Do save instructions given for writing code that should be remembered

## 5. Tests

- Does new functionality have both success and failure automated tests?


## 6. Commit and Push

```bash
git add -A
git commit -m "Type: Brief description

- Detailed change 1
- Detailed change 2"
git push -u origin <branch-name>
```

**Commit types:** `Refactor`, `Fix`, `Feature`, `Docs`, `Test`, `Chore`

## 7. Create PR

```bash
gh pr create --title "Type: Brief description" --body "## Summary
Brief description

## Changes
- Change 1
- Change 2

## Testing
✅ All tests passing"
```

## 8. Periodic Clean up

After pushing a PR, it's a good time to take care of some periodic cleanup tasks

Delete log or other files, if they exist:
- django.log
- django_errors.log
- dump.rb
