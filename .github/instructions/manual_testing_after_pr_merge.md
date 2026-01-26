# Manual Testing After PR Merge

When a PR is merged, manually test the new functionality before considering it complete.


## Step 1: Archive Requirements

1. Read the last 5 commit messages, identify recent changes, and identify the most recent feature implementation.
2. Create folder: `docs/old_requirements/<feature_name>/`.
3. If it exists, move `docs/requirements/<feature>_requirements.md` into the new folder
4. If it exists, move `docs/requirements/<feature>_implementation_plan.md` into the new folder


## Step 2: Create Test Plan

1. Read both the requirements and implementation plan documents for the last PR, if they exist
2. Review existing management commands with `python manage.py --help`
3. Create `docs/old_requirements/<feature_name>/test_plan.md` with:

```markdown
# <Feature> Test Plan

## Feature Summary
Brief description of what was implemented.

## Test Scenarios

### Scenario 1: <Happy Path>
**Goal:** Verify basic functionality works
**Command:**
```bash
python manage.py <command> --args
```
**Expected:** Description of expected output/behavior
**Actual:** [Fill in during testing]
**Status:** [ ] Pass / [ ] Fail

### Scenario 2: <Edge Case>
...

### Scenario 3: <Error Handling>
...

## Database Verification
Queries to run to verify data was created/modified correctly.

## Test Results
Date: YYYY-MM-DD
Tester: Copilot
Overall: [ ] Pass / [ ] Fail
Notes: Any issues discovered
```


## Step 3: Execute Test Plan

### Primary: Existing Management Commands

**Use existing management commands for testing whenever possible.** This is the strongly preferred testing method because:
- Commands are already tested and reliable
- They exercise real code paths end-to-end
- Output is human-readable and easy to verify
- Commands can be reused for future testing and debugging
- Avoids one-off scripts that become stale or lost

Common commands for testing:
```bash
source .venv/bin/activate

# Load theater data
python manage.py load_theaters

# TMDB search
python manage.py tmdb_service_search "Movie Title" --year 2025

# Download movies from colombia.com
python manage.py colombia_com_download_movies --theater <slug>
```

**Check available commands with `python manage.py --help`** to find the right command for testing your feature.

**If no suitable command exists:**
1. Consider creating a new management command instead of a one-off script
2. Management commands are discoverable (`python manage.py --help`)
3. They can be reused for testing, debugging, and manual operations
4. They follow project conventions and error handling patterns

### Secondary: Django Shell

Verify database state after running commands:
```bash
python manage.py shell -c "
from movies_app.models import Movie, Theater, Showtime, OperationalIssue
# Query and print results
"
```

### MCP Chrome DevTools
For browser-based features:
1. Use `mcp_chrome-devtoo_evaluate_script` to inspect page state
2. Use snapshot tools to capture page content
3. Verify JavaScript console for errors

### Last Resort: One-Off Test Scripts
**Only use one-off scripts when commands are impractical.** Before creating a script, ask:
- Could this be a management command instead?
- Will this test be needed again in the future?
- Does this test complex logic that should be reusable?

If yes to any of these, create a management command instead of a script.

For truly one-off scenarios:
```bash
# Create temporary script
cat > /tmp/test_feature.py << 'EOF'
import django
django.setup()
# Test code here
EOF

# Run it
DJANGO_PRODUCTION=1 python /tmp/test_feature.py
```

**Remember:** Delete temporary scripts after testing (see Step 5: Cleanup).

### Log Verification
Check logs for expected behavior:
- Look for INFO messages indicating success
- Verify no unexpected ERROR or WARNING messages
- Check that operational issues are created when expected

### Error Handling Tests
Intentionally trigger failures to verify graceful handling:
- Invalid input
- Missing data
- Network failures (if applicable)


## Step 4: Document Results

1. Fill in "Actual" and "Status" fields in test plan
2. If failures found:
   - Create issue or fix immediately
   - Document in test plan Notes section
3. Update test plan with:
   - Date tested
   - Overall pass/fail status
   - Any edge cases discovered


## Step 5: Cleanup

1. Delete any temporary test scripts
2. Revert any test data changes if needed
3. Confirm feature is ready for production use
