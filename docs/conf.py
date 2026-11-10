# Configuration file for the Sphinx documentation builder.
#
# For the full list of built-in configuration values, see the documentation:
# https://www.sphinx-doc.org/en/master/usage/configuration.html

# -- Project information -----------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#project-information

project = "gem5"
copyright = ""
author = ""

# -- General configuration ---------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#general-configuration

extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.viewcode",
    "sphinx.ext.todo",
]

templates_path = ["_templates"]
exclude_patterns = [
    "_build",
    "Thumbs.db",
    ".DS_Store",
    "build/lib64/python3.*/site-packages",
    "build/lib/python3.*/site-packages",
]

language = "en"

# -- Options for HTML output -------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#options-for-html-output

html_theme = "alabaster"
html_static_path = ["_static"]

# -- Options for todo extension ----------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/extensions/todo.html#configuration

todo_include_todos = True

# -- Options for Breathe (C++ Doxygen XML integration) -----------------------
import os as _os

try:
    import breathe as _breathe  # noqa: F401
    extensions.append("breathe")
    breathe_projects = {
        "gem5-SALAM": _os.environ.get(
            "SALAM_DOXYGEN_XML", "_build/doxygen/xml"
        )
    }
    breathe_default_project = "gem5-SALAM"
except ImportError:
    pass
