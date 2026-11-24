"""Path helpers for bundled resources and user-editable application files."""

import os
import sys


def get_app_dir():
    """Return the directory used for external configuration, logs, and exports."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


def get_resource_path(relative_path):
    """Return a path to a bundled resource or a source-tree resource."""
    base_path = getattr(sys, "_MEIPASS", None)
    if base_path is None:
        base_path = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_path, relative_path)
