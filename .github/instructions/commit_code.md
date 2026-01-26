# Commit Code Workflow

When asked to commit code changes, follow this workflow:

## 1. Run All Checks

```bash
source .venv/bin/activate
python manage.py check
python manage.py makemigrations --check --dry-run
ruff check .
pyright
pytest
```


## 2. Update copilot-instructions

- If there is anything important to remember, update the copilot-instructions with the new information


## 3. Commit

```bash
git add -A
git commit -m "<descriptive commit message>"
```

## Pre-Commit Checklist

- [ ] Django checks pass
- [ ] No missing migrations
- [ ] All tests passing
- [ ] Linting passes (`ruff check .`)
- [ ] Type checking passes (`pyright`)
