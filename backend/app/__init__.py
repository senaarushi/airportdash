"""
Makes `app` an explicit Python package rooted at backend/app, rather than
relying on implicit namespace-package resolution, which is sensitive to
sys.path in ways that caused real import failures (see pyproject.toml's
docstring and Context README for the full story: a stray, empty `app/`
package tree previously existed at the repo root and was shadowing/
confusing this real one, depending on where Python/pytest was invoked
from). This file, and the __init__.py in every subpackage below it, are
the actual fix, not a formality.
"""
