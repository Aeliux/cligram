"""Sphinx configuration for cligram documentation."""

import os
import sys

# Add project root to path
_src_root = os.path.abspath("../../src")
sys.path.insert(0, _src_root)

# Project information
project = "cligram"
copyright = "2025, Alireza Poodineh"
author = "Alireza Poodineh"

# Execute version retrieval
with open(os.path.join(_src_root, "cligram", "_gen_version.py")) as f:
    # extract version without importing or executing the file
    content = f.read()
    version_line = next(
        line for line in content.splitlines() if line.startswith("__version__")
    )
    release = version = version_line.split("=")[1].strip().strip('"').strip("'")

# General configuration
extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.autosummary",
    "sphinx.ext.napoleon",
    "sphinx.ext.viewcode",
    "sphinx.ext.intersphinx",
    "sphinx_autodoc_typehints",
    "myst_parser",
]

templates_path = ["_templates"]
exclude_patterns = []

# HTML output options
html_theme = "sphinx_rtd_theme"
html_static_path = ["_static"]

# Extension configuration
autosummary_generate = True  # Turn on autosummary
autosummary_imported_members = True

autodoc_default_options = {
    "members": True,
    "show-inheritance": True,
}

autodoc_mock_imports = []  # Add any problematic imports here if needed

napoleon_google_docstring = True
napoleon_numpy_docstring = False

intersphinx_mapping = {
    "python": ("https://docs.python.org/3", None),
    "telethon": ("https://docs.telethon.dev/en/stable/", None),
}

myst_enable_extensions = [
    "colon_fence",
    "deflist",
]
