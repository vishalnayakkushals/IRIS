"""Streamlit entrypoint that loads and executes the dashboard module.

This preserves package imports and avoids relative-import errors in Docker.
"""

from iris import iris_dashboard


iris_dashboard.main()
