# Code Review Checklist

When asked to review code, check the following:

## Code Quality

- [ ] No commented-out code or debug statements
- [ ] No hardcoded values (use settings/env vars)
- [ ] No synchronous calls in async code (see below)
- [ ] Tests exist for new functionality (success + failure cases)
- [ ] Exceptions logged properly

## Sync Calls in Async Code

In `async def` methods, Django ORM calls and other sync I/O will raise `SynchronousOnlyOperation`. Look for:

- Direct `Model.objects.create()`, `.save()`, `.filter()` calls
- Calling sync methods that internally do DB operations (e.g., `OperationalIssue.log_error()`)
- Any sync function that performs I/O

**Fix**: Wrap with `sync_to_async` at module level:

```python
from asgiref.sync import sync_to_async

_log_error_async = sync_to_async(OperationalIssue.log_error, thread_sensitive=True)

async def my_async_method(self):
    # ❌ Wrong - sync call in async context
    OperationalIssue.log_error(...)

    # ✅ Correct - wrapped for async
    await _log_error_async(...)

## Django-Specific

- [ ] Query optimization (`select_related`/`prefetch_related`)
- [ ] Transactions where needed (`@transaction.atomic`)
- [ ] Migration files included for model changes

## Feedback Categories

- **🔴 Blocking**: Must fix (bugs, security, test failures)
- **🟡 Important**: Should fix (performance, maintainability)
- **🟢 Suggestion**: Nice to have
