#!/usr/bin/env python3
# ==============================================================================
# generate_docs.py - Unified Documentation Generator for gem5-SALAM
# ==============================================================================
"""
Generates comprehensive documentation from all project sources.

This script collects and processes documentation from:
- Python modules (docstrings → Sphinx/HTML)
- C++ headers (Doxygen comments → HTML)
- Markdown files (→ HTML)
- Benchmark READMEs

Usage:
    python scripts/generate_docs.py              # Generate all docs
    python scripts/generate_docs.py --python     # Python docs only
    python scripts/generate_docs.py --cpp        # C++ docs only
    python scripts/generate_docs.py --markdown   # Markdown only
    python scripts/generate_docs.py --serve      # Generate and serve locally

Output:
    docs/
    ├── index.html          # Main documentation index
    ├── python/             # Sphinx-generated Python API docs
    ├── cpp/                # Doxygen-generated C++ docs
    ├── guides/             # Converted Markdown guides
    └── benchmarks/         # Benchmark documentation
"""

import os
import sys
import shutil
import subprocess
import argparse
import re
from pathlib import Path
from typing import List, Optional
from datetime import datetime


class DocumentationGenerator:
    """Unified documentation generator for gem5-SALAM project."""

    def __init__(self, project_root: Path):
        """Initialize generator with project root path."""
        self.project_root = project_root
        self.docs_dir = project_root / "docs"
        self.build_dir = project_root / "docs" / "_build"

    def generate_all(self):
        """Generate all documentation."""
        print("=" * 60)
        print("gem5-SALAM Documentation Generator")
        print("=" * 60)

        self._setup_docs_directory()
        self.generate_markdown_docs()
        self.generate_python_docs()
        self.generate_cpp_docs()
        self.generate_index()

        print("\n" + "=" * 60)
        print(f"Documentation generated in: {self.docs_dir}")
        print("=" * 60)

    def _setup_docs_directory(self):
        """Create docs directory structure."""
        print("\n[1/5] Setting up documentation directory...")

        # Create directory structure
        dirs = [
            self.docs_dir,
            self.docs_dir / "python",
            self.docs_dir / "cpp",
            self.docs_dir / "guides",
            self.docs_dir / "benchmarks",
            self.docs_dir / "_static",
        ]

        for d in dirs:
            d.mkdir(parents=True, exist_ok=True)

        # Copy CSS
        self._create_stylesheet()
        print(f"  Created: {self.docs_dir}")

    def _create_stylesheet(self):
        """Create custom CSS stylesheet."""
        css = """
/* gem5-SALAM Documentation Stylesheet */
:root {
    --primary-color: #2c3e50;
    --secondary-color: #3498db;
    --bg-color: #ffffff;
    --text-color: #333333;
    --code-bg: #f4f4f4;
    --border-color: #e0e0e0;
}

body {
    font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
    line-height: 1.6;
    color: var(--text-color);
    max-width: 1200px;
    margin: 0 auto;
    padding: 20px;
    background: var(--bg-color);
}

h1, h2, h3, h4 {
    color: var(--primary-color);
    margin-top: 1.5em;
}

h1 {
    border-bottom: 3px solid var(--secondary-color);
    padding-bottom: 10px;
}

h2 {
    border-bottom: 1px solid var(--border-color);
    padding-bottom: 5px;
}

a {
    color: var(--secondary-color);
    text-decoration: none;
}

a:hover {
    text-decoration: underline;
}

pre, code {
    background: var(--code-bg);
    border-radius: 4px;
    font-family: 'Consolas', 'Monaco', monospace;
}

pre {
    padding: 15px;
    overflow-x: auto;
    border: 1px solid var(--border-color);
}

code {
    padding: 2px 6px;
}

table {
    border-collapse: collapse;
    width: 100%;
    margin: 1em 0;
}

th, td {
    border: 1px solid var(--border-color);
    padding: 10px;
    text-align: left;
}

th {
    background: var(--code-bg);
    font-weight: 600;
}

.nav {
    background: var(--primary-color);
    padding: 15px;
    margin: -20px -20px 20px -20px;
}

.nav a {
    color: white;
    margin-right: 20px;
    font-weight: 500;
}

.nav a:hover {
    text-decoration: none;
    opacity: 0.8;
}

.card {
    border: 1px solid var(--border-color);
    border-radius: 8px;
    padding: 20px;
    margin: 15px 0;
    transition: box-shadow 0.2s;
}

.card:hover {
    box-shadow: 0 4px 12px rgba(0,0,0,0.1);
}

.card h3 {
    margin-top: 0;
    color: var(--secondary-color);
}

.grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
    gap: 20px;
}

.footer {
    margin-top: 50px;
    padding-top: 20px;
    border-top: 1px solid var(--border-color);
    text-align: center;
    color: #666;
    font-size: 0.9em;
}
"""
        (self.docs_dir / "_static" / "style.css").write_text(css)

    def generate_markdown_docs(self):
        """Convert Markdown files to HTML."""
        print("\n[2/5] Converting Markdown documentation...")

        # Find all markdown files
        md_files = list(self.project_root.glob("*.md"))
        md_files += list(self.project_root.glob("benchmarks/**/*.md"))
        md_files += list(self.project_root.glob("scripts/**/*.md"))

        converted = 0
        for md_file in md_files:
            try:
                html = self._markdown_to_html(md_file)

                # Determine output path
                rel_path = md_file.relative_to(self.project_root)
                if str(rel_path).startswith("benchmarks"):
                    out_dir = self.docs_dir / "benchmarks"
                else:
                    out_dir = self.docs_dir / "guides"

                out_file = out_dir / (md_file.stem + ".html")
                out_file.parent.mkdir(parents=True, exist_ok=True)
                out_file.write_text(html)
                converted += 1

            except Exception as e:
                print(f"  Warning: Could not convert {md_file}: {e}")

        print(f"  Converted {converted} Markdown files")

    def _markdown_to_html(self, md_file: Path) -> str:
        """Convert a Markdown file to styled HTML."""
        content = md_file.read_text(encoding='utf-8', errors='ignore')
        title = md_file.stem.replace('_', ' ').replace('-', ' ').title()

        # Extract title from first heading if present
        match = re.search(r'^#\s+(.+)$', content, re.MULTILINE)
        if match:
            title = match.group(1)

        html_body = self._convert_markdown(content)

        return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title} - gem5-SALAM Documentation</title>
    <link rel="stylesheet" href="../_static/style.css">
</head>
<body>
    <nav class="nav">
        <a href="../index.html">Home</a>
        <a href="../guides/README.html">Guides</a>
        <a href="../benchmarks/README.html">Benchmarks</a>
        <a href="../python/index.html">Python API</a>
        <a href="../cpp/index.html">C++ API</a>
    </nav>

    {html_body}

    <div class="footer">
        <p>gem5-SALAM Documentation | Generated {datetime.now().strftime('%Y-%m-%d %H:%M')}</p>
    </div>
</body>
</html>
"""

    def _convert_markdown(self, text: str) -> str:
        """Convert Markdown text to HTML."""
        html = text

        # Code blocks (```lang\n...\n```)
        def replace_code_block(match):
            lang = match.group(1) or ''
            code = match.group(2)
            code = code.replace('<', '&lt;').replace('>', '&gt;')
            return f'<pre><code class="language-{lang}">{code}</code></pre>'

        html = re.sub(r'```(\w*)\n(.*?)```', replace_code_block, html, flags=re.DOTALL)

        # Inline code
        html = re.sub(r'`([^`]+)`', r'<code>\1</code>', html)

        # Headers
        html = re.sub(r'^#### (.+)$', r'<h4>\1</h4>', html, flags=re.MULTILINE)
        html = re.sub(r'^### (.+)$', r'<h3>\1</h3>', html, flags=re.MULTILINE)
        html = re.sub(r'^## (.+)$', r'<h2>\1</h2>', html, flags=re.MULTILINE)
        html = re.sub(r'^# (.+)$', r'<h1>\1</h1>', html, flags=re.MULTILINE)

        # Bold and italic
        html = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', html)
        html = re.sub(r'\*(.+?)\*', r'<em>\1</em>', html)

        # Links
        html = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'<a href="\2">\1</a>', html)

        # Lists
        lines = html.split('\n')
        result = []
        in_list = False

        for line in lines:
            if re.match(r'^[-*]\s+', line):
                if not in_list:
                    result.append('<ul>')
                    in_list = True
                item = re.sub(r'^[-*]\s+', '', line)
                result.append(f'<li>{item}</li>')
            else:
                if in_list:
                    result.append('</ul>')
                    in_list = False
                result.append(line)

        if in_list:
            result.append('</ul>')

        html = '\n'.join(result)

        # Tables
        html = self._convert_tables(html)

        # Paragraphs (double newline)
        html = re.sub(r'\n\n+', '</p>\n<p>', html)
        html = f'<p>{html}</p>'

        # Clean up empty paragraphs
        html = re.sub(r'<p>\s*</p>', '', html)
        html = re.sub(r'<p>\s*<(h[1-4]|ul|ol|pre|table)', r'<\1', html)
        html = re.sub(r'</(h[1-4]|ul|ol|pre|table)>\s*</p>', r'</\1>', html)

        return html

    def _convert_tables(self, html: str) -> str:
        """Convert Markdown tables to HTML."""
        lines = html.split('\n')
        result = []
        in_table = False
        header_done = False

        for line in lines:
            # Check if this is a table row
            if '|' in line and line.strip().startswith('|'):
                cells = [c.strip() for c in line.split('|')[1:-1]]

                # Skip separator row
                if all(re.match(r'^[-:]+$', c) for c in cells):
                    continue

                if not in_table:
                    result.append('<table>')
                    in_table = True
                    header_done = False

                if not header_done:
                    result.append('<thead><tr>')
                    result.append(''.join(f'<th>{c}</th>' for c in cells))
                    result.append('</tr></thead><tbody>')
                    header_done = True
                else:
                    result.append('<tr>')
                    result.append(''.join(f'<td>{c}</td>' for c in cells))
                    result.append('</tr>')
            else:
                if in_table:
                    result.append('</tbody></table>')
                    in_table = False
                result.append(line)

        if in_table:
            result.append('</tbody></table>')

        return '\n'.join(result)

    def generate_python_docs(self):
        """Generate Python API documentation using Sphinx or pydoc."""
        print("\n[3/5] Generating Python API documentation...")

        python_doc_dir = self.docs_dir / "python"

        # Check if Sphinx is available
        try:
            subprocess.run(["sphinx-build", "--version"],
                         capture_output=True, check=True)
            self._generate_sphinx_docs(python_doc_dir)
        except (subprocess.CalledProcessError, FileNotFoundError):
            print("  Sphinx not found, using built-in generator...")
            self._generate_simple_python_docs(python_doc_dir)

    def _generate_sphinx_docs(self, output_dir: Path):
        """Generate docs using Sphinx."""
        sphinx_dir = self.project_root / "docs" / "_sphinx"
        sphinx_dir.mkdir(exist_ok=True)

        # Create conf.py
        conf_py = f'''
project = "gem5-SALAM"
copyright = "{datetime.now().year}, gem5-SALAM Team"
author = "gem5-SALAM Team"

extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.viewcode",
    "sphinx.ext.napoleon",
]

templates_path = ["_templates"]
exclude_patterns = ["_build"]
html_theme = "alabaster"
html_static_path = ["_static"]
'''
        (sphinx_dir / "conf.py").write_text(conf_py)

        # Create index.rst
        index_rst = '''
gem5-SALAM Python API
=====================

.. toctree::
   :maxdepth: 2
   :caption: Contents:

   modules

Indices and tables
==================

* :ref:`genindex`
* :ref:`modindex`
'''
        (sphinx_dir / "index.rst").write_text(index_rst)

        # Run sphinx-apidoc
        subprocess.run([
            "sphinx-apidoc", "-o", str(sphinx_dir),
            str(self.project_root / "scripts" / "salam_gui"),
            "--force"
        ], capture_output=True)

        # Run sphinx-build
        result = subprocess.run([
            "sphinx-build", "-b", "html",
            str(sphinx_dir), str(output_dir)
        ], capture_output=True)

        if result.returncode == 0:
            print(f"  Sphinx documentation generated: {output_dir}")
        else:
            print(f"  Sphinx failed, falling back to simple generator")
            self._generate_simple_python_docs(output_dir)

    def _generate_simple_python_docs(self, output_dir: Path):
        """Generate simple Python documentation without Sphinx."""
        gui_dir = self.project_root / "scripts" / "salam_gui"

        modules = []

        # Process all Python files
        for py_file in gui_dir.rglob("*.py"):
            if py_file.name.startswith("__"):
                continue

            try:
                content = py_file.read_text(encoding='utf-8', errors='ignore')
                doc = self._extract_python_docs(py_file, content)

                rel_path = py_file.relative_to(gui_dir)
                module_name = str(rel_path).replace('/', '.').replace('\\', '.')[:-3]

                modules.append({
                    'name': module_name,
                    'file': py_file.name,
                    'doc': doc
                })

                # Write individual module page
                out_file = output_dir / f"{module_name}.html"
                out_file.write_text(self._create_module_page(module_name, doc))

            except Exception as e:
                print(f"  Warning: Could not process {py_file}: {e}")

        # Create index
        index_html = self._create_python_index(modules)
        (output_dir / "index.html").write_text(index_html)

        print(f"  Generated docs for {len(modules)} Python modules")

    def _extract_python_docs(self, filepath: Path, content: str) -> dict:
        """Extract documentation from a Python file."""
        doc = {
            'module_doc': '',
            'classes': [],
            'functions': []
        }

        # Extract module docstring
        match = re.search(r'^"""(.+?)"""', content, re.DOTALL)
        if match:
            doc['module_doc'] = match.group(1).strip()

        # Extract class definitions and docstrings
        class_pattern = r'class\s+(\w+)(?:\([^)]*\))?:\s*(?:"""(.+?)""")?'
        for match in re.finditer(class_pattern, content, re.DOTALL):
            doc['classes'].append({
                'name': match.group(1),
                'doc': (match.group(2) or '').strip()
            })

        # Extract function definitions and docstrings
        func_pattern = r'def\s+(\w+)\s*\([^)]*\)(?:\s*->\s*[^:]+)?:\s*(?:"""(.+?)""")?'
        for match in re.finditer(func_pattern, content, re.DOTALL):
            if not match.group(1).startswith('_') or match.group(1) == '__init__':
                doc['functions'].append({
                    'name': match.group(1),
                    'doc': (match.group(2) or '').strip()
                })

        return doc

    def _create_module_page(self, module_name: str, doc: dict) -> str:
        """Create HTML page for a Python module."""
        classes_html = ""
        if doc['classes']:
            classes_html = "<h2>Classes</h2>"
            for cls in doc['classes']:
                classes_html += f"""
                <div class="card">
                    <h3><code>class {cls['name']}</code></h3>
                    <p>{cls['doc'] or 'No documentation available.'}</p>
                </div>
                """

        functions_html = ""
        if doc['functions']:
            functions_html = "<h2>Functions</h2>"
            for func in doc['functions']:
                functions_html += f"""
                <div class="card">
                    <h3><code>{func['name']}()</code></h3>
                    <p>{func['doc'] or 'No documentation available.'}</p>
                </div>
                """

        return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>{module_name} - gem5-SALAM Python API</title>
    <link rel="stylesheet" href="../_static/style.css">
</head>
<body>
    <nav class="nav">
        <a href="../index.html">Home</a>
        <a href="index.html">Python API</a>
        <a href="../cpp/index.html">C++ API</a>
    </nav>

    <h1>{module_name}</h1>

    <div class="module-doc">
        <pre>{doc['module_doc'] or 'No module documentation available.'}</pre>
    </div>

    {classes_html}
    {functions_html}

    <div class="footer">
        <p>gem5-SALAM Documentation | Generated {datetime.now().strftime('%Y-%m-%d %H:%M')}</p>
    </div>
</body>
</html>
"""

    def _create_python_index(self, modules: List[dict]) -> str:
        """Create Python documentation index page."""
        modules_html = ""

        # Group by subpackage
        grouped = {}
        for mod in modules:
            parts = mod['name'].split('.')
            group = parts[0] if len(parts) > 1 else 'core'
            if group not in grouped:
                grouped[group] = []
            grouped[group].append(mod)

        for group, mods in sorted(grouped.items()):
            modules_html += f"<h2>{group.title()}</h2><div class='grid'>"
            for mod in sorted(mods, key=lambda x: x['name']):
                first_line = (mod['doc']['module_doc'] or 'No description').split('\n')[0][:100]
                modules_html += f"""
                <div class="card">
                    <h3><a href="{mod['name']}.html">{mod['name']}</a></h3>
                    <p>{first_line}</p>
                </div>
                """
            modules_html += "</div>"

        return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Python API - gem5-SALAM Documentation</title>
    <link rel="stylesheet" href="../_static/style.css">
</head>
<body>
    <nav class="nav">
        <a href="../index.html">Home</a>
        <a href="../guides/README.html">Guides</a>
        <a href="../benchmarks/README.html">Benchmarks</a>
        <a href="index.html">Python API</a>
        <a href="../cpp/index.html">C++ API</a>
    </nav>

    <h1>Python API Reference</h1>
    <p>API documentation for the gem5-SALAM GUI and tools.</p>

    {modules_html}

    <div class="footer">
        <p>gem5-SALAM Documentation | Generated {datetime.now().strftime('%Y-%m-%d %H:%M')}</p>
    </div>
</body>
</html>
"""

    def generate_cpp_docs(self):
        """Generate C++ API documentation using Doxygen."""
        print("\n[4/5] Generating C++ API documentation...")

        cpp_doc_dir = self.docs_dir / "cpp"

        # Check if Doxygen is available
        try:
            subprocess.run(["doxygen", "--version"],
                         capture_output=True, check=True)
            self._generate_doxygen_docs(cpp_doc_dir)
        except (subprocess.CalledProcessError, FileNotFoundError):
            print("  Doxygen not found, generating simple C++ docs...")
            self._generate_simple_cpp_docs(cpp_doc_dir)

    def _generate_doxygen_docs(self, output_dir: Path):
        """Generate docs using Doxygen."""
        doxyfile = self.project_root / "Doxyfile"

        # Create Doxyfile
        doxyfile_content = f"""
PROJECT_NAME           = "gem5-SALAM"
PROJECT_BRIEF          = "System-level Architecture for Modeling Hardware Accelerators"
OUTPUT_DIRECTORY       = {output_dir}
INPUT                  = {self.project_root / "src"}
FILE_PATTERNS          = *.hh *.cc *.h *.cpp
RECURSIVE              = YES
GENERATE_HTML          = YES
GENERATE_LATEX         = NO
HTML_OUTPUT            = .
EXTRACT_ALL            = YES
EXTRACT_PRIVATE        = NO
EXTRACT_STATIC         = YES
SOURCE_BROWSER         = YES
INLINE_SOURCES         = NO
GENERATE_TREEVIEW      = YES
"""
        doxyfile.write_text(doxyfile_content)

        # Run Doxygen
        result = subprocess.run(
            ["doxygen", str(doxyfile)],
            cwd=self.project_root,
            capture_output=True
        )

        if result.returncode == 0:
            print(f"  Doxygen documentation generated: {output_dir}")
        else:
            print(f"  Doxygen failed: {result.stderr.decode()[:200]}")
            self._generate_simple_cpp_docs(output_dir)

    def _generate_simple_cpp_docs(self, output_dir: Path):
        """Generate simple C++ documentation without Doxygen."""
        src_dir = self.project_root / "src"

        if not src_dir.exists():
            print("  No src/ directory found, skipping C++ docs")
            self._create_placeholder_cpp_index(output_dir)
            return

        headers = list(src_dir.rglob("*.hh")) + list(src_dir.rglob("*.h"))

        docs = []
        for header in headers[:50]:  # Limit to first 50
            try:
                content = header.read_text(encoding='utf-8', errors='ignore')
                doc = self._extract_cpp_docs(header, content)
                if doc['classes'] or doc['functions']:
                    docs.append({
                        'file': header.name,
                        'path': str(header.relative_to(self.project_root)),
                        'doc': doc
                    })
            except Exception:
                pass

        # Create index
        index_html = self._create_cpp_index(docs)
        (output_dir / "index.html").write_text(index_html)

        print(f"  Generated docs for {len(docs)} C++ headers")

    def _extract_cpp_docs(self, filepath: Path, content: str) -> dict:
        """Extract documentation from a C++ header."""
        doc = {
            'file_doc': '',
            'classes': [],
            'functions': []
        }

        # Extract file documentation
        match = re.search(r'/\*\*(.+?)\*/', content, re.DOTALL)
        if match:
            doc['file_doc'] = match.group(1).strip()

        # Extract class definitions
        class_pattern = r'class\s+(\w+)(?:\s*:\s*[^{]+)?\s*\{'
        for match in re.finditer(class_pattern, content):
            doc['classes'].append({'name': match.group(1)})

        return doc

    def _create_cpp_index(self, docs: List[dict]) -> str:
        """Create C++ documentation index."""
        content = ""
        for doc in docs:
            classes = ', '.join(c['name'] for c in doc['doc']['classes'][:5])
            content += f"""
            <div class="card">
                <h3>{doc['file']}</h3>
                <p><code>{doc['path']}</code></p>
                <p>Classes: {classes or 'None'}</p>
            </div>
            """

        return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>C++ API - gem5-SALAM Documentation</title>
    <link rel="stylesheet" href="../_static/style.css">
</head>
<body>
    <nav class="nav">
        <a href="../index.html">Home</a>
        <a href="../guides/README.html">Guides</a>
        <a href="../python/index.html">Python API</a>
        <a href="index.html">C++ API</a>
    </nav>

    <h1>C++ API Reference</h1>
    <p>API documentation for the gem5-SALAM simulation framework.</p>
    <p><em>Install Doxygen for full C++ documentation generation.</em></p>

    <div class="grid">
        {content}
    </div>

    <div class="footer">
        <p>gem5-SALAM Documentation | Generated {datetime.now().strftime('%Y-%m-%d %H:%M')}</p>
    </div>
</body>
</html>
"""

    def _create_placeholder_cpp_index(self, output_dir: Path):
        """Create placeholder C++ index when no source is available."""
        html = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>C++ API - gem5-SALAM Documentation</title>
    <link rel="stylesheet" href="../_static/style.css">
</head>
<body>
    <nav class="nav">
        <a href="../index.html">Home</a>
        <a href="../python/index.html">Python API</a>
        <a href="index.html">C++ API</a>
    </nav>

    <h1>C++ API Reference</h1>
    <p>Install Doxygen and run the documentation generator to create C++ API documentation.</p>
    <pre>sudo apt install doxygen
python scripts/generate_docs.py --cpp</pre>

    <div class="footer">
        <p>gem5-SALAM Documentation</p>
    </div>
</body>
</html>
"""
        (output_dir / "index.html").write_text(html)

    def generate_index(self):
        """Generate main documentation index page."""
        print("\n[5/5] Generating documentation index...")

        index_html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>gem5-SALAM Documentation</title>
    <link rel="stylesheet" href="_static/style.css">
</head>
<body>
    <nav class="nav">
        <a href="index.html">Home</a>
        <a href="guides/README.html">Guides</a>
        <a href="benchmarks/README.html">Benchmarks</a>
        <a href="python/index.html">Python API</a>
        <a href="cpp/index.html">C++ API</a>
    </nav>

    <h1>gem5-SALAM Documentation</h1>
    <p>Comprehensive documentation for the gem5-SALAM hardware accelerator simulation framework.</p>

    <div class="grid">
        <div class="card">
            <h3><a href="guides/README.html">Getting Started</a></h3>
            <p>Installation instructions, quick start guide, and basic tutorials.</p>
        </div>

        <div class="card">
            <h3><a href="benchmarks/README.html">Benchmarks</a></h3>
            <p>Benchmark suite documentation including GEMM, FFT, neural networks, and more.</p>
        </div>

        <div class="card">
            <h3><a href="python/index.html">Python API</a></h3>
            <p>GUI widgets, data parsers, and Python tool documentation.</p>
        </div>

        <div class="card">
            <h3><a href="cpp/index.html">C++ API</a></h3>
            <p>Core simulation framework, accelerator models, and instruction classes.</p>
        </div>
    </div>

    <h2>Quick Links</h2>
    <ul>
        <li><a href="guides/README.html">Project README</a></li>
        <li><a href="benchmarks/README.html">Benchmarks Overview</a></li>
        <li><a href="benchmarks/legacy/README.html">Legacy Benchmarks</a></li>
        <li><a href="python/main_window.html">GUI Main Window</a></li>
    </ul>

    <h2>GUI Features</h2>
    <ul>
        <li>CDFG Visualization</li>
        <li>Statistics Dashboard</li>
        <li>Queue Monitoring</li>
        <li>FU Utilization Heatmaps</li>
        <li>Execution Timeline</li>
        <li>Real-time Simulation Connection</li>
    </ul>

    <div class="footer">
        <p>gem5-SALAM Documentation | Generated {datetime.now().strftime('%Y-%m-%d %H:%M')}</p>
        <p>Access in-app help via <strong>Help → Help Contents (F1)</strong></p>
    </div>
</body>
</html>
"""
        (self.docs_dir / "index.html").write_text(index_html)
        print(f"  Created: {self.docs_dir / 'index.html'}")

    def serve(self, port: int = 8000):
        """Start a local HTTP server to view documentation."""
        import http.server
        import socketserver

        os.chdir(self.docs_dir)

        handler = http.server.SimpleHTTPRequestHandler
        with socketserver.TCPServer(("", port), handler) as httpd:
            print(f"\nServing documentation at http://localhost:{port}")
            print("Press Ctrl+C to stop")
            httpd.serve_forever()


def main():
    parser = argparse.ArgumentParser(
        description='Generate gem5-SALAM documentation',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    python scripts/generate_docs.py              # Generate all docs
    python scripts/generate_docs.py --serve      # Generate and serve locally
    python scripts/generate_docs.py --python     # Python docs only
"""
    )

    parser.add_argument('--python', action='store_true',
                       help='Generate Python documentation only')
    parser.add_argument('--cpp', action='store_true',
                       help='Generate C++ documentation only')
    parser.add_argument('--markdown', action='store_true',
                       help='Generate Markdown documentation only')
    parser.add_argument('--serve', action='store_true',
                       help='Start local server after generation')
    parser.add_argument('--port', type=int, default=8000,
                       help='Port for local server (default: 8000)')
    parser.add_argument('--output', type=str,
                       help='Output directory (default: docs/)')

    args = parser.parse_args()

    # Determine project root
    script_path = Path(__file__).resolve()
    project_root = script_path.parent.parent

    # If in scripts/ directory, go up one level
    if project_root.name == 'scripts':
        project_root = project_root.parent

    generator = DocumentationGenerator(project_root)

    if args.output:
        generator.docs_dir = Path(args.output)

    # Generate requested docs
    if args.python or args.cpp or args.markdown:
        generator._setup_docs_directory()
        if args.python:
            generator.generate_python_docs()
        if args.cpp:
            generator.generate_cpp_docs()
        if args.markdown:
            generator.generate_markdown_docs()
        generator.generate_index()
    else:
        generator.generate_all()

    if args.serve:
        generator.serve(args.port)


if __name__ == '__main__':
    main()
