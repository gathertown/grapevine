"""Category definitions for category-based PR review."""

from enum import Enum


class Category(Enum):
    """Review categories for organizing PR feedback."""

    CORRECTNESS = "correctness"  # Bugs, logic errors, type issues
    PERFORMANCE = "performance"  # O(n²), memory leaks, unnecessary work
    SECURITY = "security"  # Auth bypass, injection, data exposure
    RELIABILITY = "reliability"  # Backwards compat, race conditions, edge cases
    # ERROR_HANDLING = "error_handling"  # Exception handling, graceful degradation, recovery
    # Test coversage is likely to be perceived as noisy, so we're not including it for now
    # Might add it back in if we can tune it to the expectations of the specific repo / team
    # TEST_COVERAGE = "test_coverage"  # Missing tests, test quality
    # MAINTAINABILITY = "maintainability"  # Readability, complexity, technical debt
    # DOCUMENTATION = "documentation"  # Missing/outdated docs, comments, API docs
    # STYLE = "style"  # Conventions, naming, formatting

    def __str__(self) -> str:
        """Return the string value of the category."""
        return self.value


# All categories for parallel review
ALL_CATEGORIES = list(Category)

# Valid category values for output validation (includes "other" for general agent)
VALID_CATEGORY_VALUES = {cat.value for cat in Category} | {"other"}
