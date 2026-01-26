Do a code review and refactor of all tests:

## Test Framework
- Is pytest used everywhere, and properly?
- Are fixtures from conftest.py used instead of direct Model.objects.create()?
- When creating fixtures, are unnecessary parameters sent in when default parameters will work?
- Are mocks/patches properly scoped and cleaned up?
- Does pytest actually pick up the test (occasionally a test is not picked up)

## Code Quality
- Are there any code smells?
- Is there duplicated setup code that should be a fixture?
- Are assertions clear and specific (not just `assert result`)?

## Test Value
- Are there any useless tests (testing Django/library behavior)?
- Are there tests that always pass regardless of implementation?
- Are failure cases tested, not just happy paths?

## Organization
- Do test class/method names clearly describe what's being tested?
- Are related tests grouped together?
- Are integration vs unit tests in appropriate locations?

## Maintenance
- Are there tests for deprecated code that should be removed?
- Are there TODO comments in tests that need addressing?
- Do tests use realistic data (HTML snapshots) vs fake minimal data?

## Code Coverage
- Run `pytest --cov=movies_app --cov-report=html`
- Open `htmlcov/index.html` to review coverage report
- Identify core functionality with low or no coverage:
  - Models and their methods
  - Services (especially business logic)
  - Celery tasks
  - Management commands
- Prioritize writing tests for:
  - Code paths that handle errors or edge cases
  - Functions with complex conditional logic
  - Public APIs and service interfaces
- Ignore coverage for:
  - Migration files
  - Admin configurations
  - Simple getters/setters