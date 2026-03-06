"""Streamlit entrypoint that loads the dashboard as a package module.

This avoids relative-import errors when running inside containers.
"""

from iris import iris_dashboard  # noqa: F401  # imported for Streamlit side effects
