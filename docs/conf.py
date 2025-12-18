# =============================================================================
# gem5-SALAM Sphinx Configuration
# =============================================================================
# This is the Sphinx configuration file for generating unified documentation
# that combines C++ (via Doxygen + Breathe) and Python (via autodoc).
#
# Usage:
#   cd docs
#   make html      # Generate HTML documentation
#   make latexpdf  # Generate PDF documentation
#
# Or use the unified script:
#   ./scripts/generate_docs.sh --html
# =============================================================================

import os
import sys
from datetime import datetime

# -- Path Setup --------------------------------------------------------------
# Add paths for Python module autodoc
# These paths are relative to the docs/ directory

project_root = os.path.abspath('..')
sys.path.insert(0, os.path.join(project_root, 'src', 'hwacc'))
sys.path.insert(0, os.path.join(project_root, 'configs', 'SALAM'))
sys.path.insert(0, os.path.join(project_root, 'scripts', 'salam_gui'))

# -- Project Information -----------------------------------------------------

project = 'gem5-SALAM'
copyright = f'{datetime.now().year}, gem5-SALAM Team'
author = 'gem5-SALAM Team'
release = '1.0.0'
version = '1.0'

# -- General Configuration ---------------------------------------------------

extensions = [
    # Core Sphinx extensions
    'sphinx.ext.autodoc',           # Python autodoc
    'sphinx.ext.autosummary',       # Generate summary tables
    'sphinx.ext.napoleon',          # Google-style docstrings
    'sphinx.ext.viewcode',          # Source code links
    'sphinx.ext.intersphinx',       # Cross-project references
    'sphinx.ext.todo',              # TODO directive support
    'sphinx.ext.coverage',          # Documentation coverage reports
    'sphinx.ext.graphviz',          # Graphviz diagrams

    # C++ documentation via Doxygen
    'breathe',                      # Doxygen XML integration

    # Theme
    'sphinx_rtd_theme',             # Read the Docs theme
]

# Master document
master_doc = 'index'

# File extensions to consider as source
source_suffix = {
    '.rst': 'restructuredtext',
    '.md': 'markdown',
}

# Patterns to exclude
exclude_patterns = [
    '_build',
    'Thumbs.db',
    '.DS_Store',
    '**.ipynb_checkpoints',
]

# Template paths
templates_path = ['_templates']

# Static files
html_static_path = ['_static']

# Pygments syntax highlighting style
pygments_style = 'sphinx'

# -- Breathe Configuration (C++ from Doxygen) --------------------------------

# Path to Doxygen XML output
breathe_projects = {
    'gem5-SALAM': '_build/doxygen/xml'
}
breathe_default_project = 'gem5-SALAM'

# Default members to show
breathe_default_members = ('members', 'undoc-members')

# Domain handling
breathe_domain_by_extension = {
    'hh': 'cpp',
    'cc': 'cpp',
    'h': 'c',
    'c': 'c',
}

# -- Napoleon Settings (Google-style Docstrings) -----------------------------

napoleon_google_docstring = True
napoleon_numpy_docstring = False
napoleon_include_init_with_doc = True
napoleon_include_private_with_doc = True
napoleon_include_special_with_doc = True
napoleon_use_admonition_for_examples = True
napoleon_use_admonition_for_notes = True
napoleon_use_admonition_for_references = False
napoleon_use_ivar = False
napoleon_use_param = True
napoleon_use_rtype = True
napoleon_use_keyword = True
napoleon_preprocess_types = True
napoleon_type_aliases = None
napoleon_attr_annotations = True

# -- Autodoc Settings --------------------------------------------------------

autodoc_default_options = {
    'members': True,
    'member-order': 'bysource',
    'special-members': '__init__',
    'undoc-members': True,
    'show-inheritance': True,
    'inherited-members': False,
    'exclude-members': '__weakref__',
}

# Mock imports for modules that may not be available during doc build
autodoc_mock_imports = [
    'm5',
    'm5.objects',
    'm5.params',
    'm5.util',
    'm5.SimObject',
    'gem5',
    'PyQt5',
    'PyQt6',
    'PySide6',
]

# Type hints
autodoc_typehints = 'description'
autodoc_typehints_description_target = 'documented'

# -- Autosummary Settings ----------------------------------------------------

autosummary_generate = True
autosummary_imported_members = False

# -- Intersphinx Configuration -----------------------------------------------

intersphinx_mapping = {
    'python': ('https://docs.python.org/3', None),
    'numpy': ('https://numpy.org/doc/stable/', None),
}

# -- TODO Extension Settings -------------------------------------------------

todo_include_todos = True
todo_emit_warnings = False

# -- HTML Output Configuration -----------------------------------------------

html_theme = 'sphinx_rtd_theme'

html_theme_options = {
    'logo_only': False,
    'display_version': True,
    'prev_next_buttons_location': 'bottom',
    'style_external_links': True,
    # TOC options
    'collapse_navigation': False,
    'sticky_navigation': True,
    'navigation_depth': 4,
    'includehidden': True,
    'titles_only': False,
}

# HTML context for templates
html_context = {
    'display_github': True,
    'github_user': 'TeCSAR-UNCC',
    'github_repo': 'gem5-SALAM',
    'github_version': 'main',
    'conf_py_path': '/docs/',
}

# Additional HTML options
html_show_sourcelink = True
html_show_sphinx = True
html_show_copyright = True

# HTML title
html_title = f'{project} v{release}'
html_short_title = project

# Favicon and logo (create these files if desired)
# html_favicon = '_static/favicon.ico'
# html_logo = '_static/logo.png'

# -- LaTeX Output Configuration ----------------------------------------------

latex_elements = {
    'papersize': 'letterpaper',
    'pointsize': '11pt',
    'preamble': r'''
\usepackage{charter}
\usepackage[defaultsans]{lato}
\usepackage{inconsolata}
''',
    'figure_align': 'htbp',
}

latex_documents = [
    (master_doc, 'gem5-SALAM.tex', 'gem5-SALAM Documentation',
     'gem5-SALAM Team', 'manual'),
]

# -- Man Page Output Configuration -------------------------------------------

man_pages = [
    (master_doc, 'gem5-salam', 'gem5-SALAM Documentation',
     [author], 1)
]

# -- Texinfo Output Configuration --------------------------------------------

texinfo_documents = [
    (master_doc, 'gem5-SALAM', 'gem5-SALAM Documentation',
     author, 'gem5-SALAM', 'System-Level Accelerator Modeling for gem5.',
     'Miscellaneous'),
]

# -- Extension Configuration -------------------------------------------------

# Graphviz
graphviz_output_format = 'svg'

# -- Custom Setup ------------------------------------------------------------

def setup(app):
    """Custom Sphinx setup hook."""
    # Add custom CSS if it exists
    css_file = '_static/custom.css'
    if os.path.exists(os.path.join(app.confdir, css_file)):
        app.add_css_file(css_file)
