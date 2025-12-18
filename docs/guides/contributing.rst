.. _contributing:

============
Contributing
============

Thank you for your interest in contributing to gem5-SALAM! This guide covers
coding standards, documentation requirements, and the contribution process.

Getting Started
===============

1. Fork the repository on GitHub
2. Clone your fork locally
3. Create a feature branch
4. Make your changes
5. Submit a pull request

Code Style
==========

C++ Style
---------

Follow the gem5 coding style:

.. code-block:: cpp

   /**
    * @brief Brief description of the class.
    *
    * Detailed description of what the class does and how to use it.
    */
   class MyClass : public BaseClass
   {
     public:
       /**
        * @brief Brief description of the method.
        *
        * @param param1 Description of first parameter.
        * @param param2 Description of second parameter.
        * @return Description of return value.
        */
       ReturnType methodName(Type param1, Type param2);

     private:
       int memberVariable;  ///< Brief description
   };

Key points:

- Use 4-space indentation
- Braces on new lines for classes/functions
- CamelCase for class names
- camelCase for method and variable names
- Doxygen comments for all public APIs

Python Style
------------

Follow PEP 8 with Google-style docstrings:

.. code-block:: python

   """Module docstring describing the module's purpose.

   This module provides functionality for...

   Example:
       Basic usage::

           from module import MyClass
           obj = MyClass()
   """

   class MyClass:
       """Brief description of the class.

       Detailed description of what the class does.

       Attributes:
           attr1: Description of attr1.
           attr2: Description of attr2.

       Example:
           Example usage::

               obj = MyClass(param1, param2)
               result = obj.method()
       """

       def method_name(self, param1: str, param2: int) -> bool:
           """Brief description of the method.

           Detailed description if needed.

           Args:
               param1: Description of param1.
               param2: Description of param2.

           Returns:
               Description of return value.

           Raises:
               ValueError: When invalid input provided.
           """
           pass

Documentation Standards
=======================

All code contributions must include documentation:

C++ Documentation (Doxygen)
---------------------------

Required elements:

- ``@file`` - File description at top
- ``@class`` - Class description
- ``@brief`` - One-line summary
- ``@param`` - Parameter descriptions
- ``@return`` - Return value description
- ``@throws`` - Exceptions thrown

Example:

.. code-block:: cpp

   /**
    * @file my_component.hh
    * @brief Header for MyComponent class.
    *
    * This file contains the MyComponent class which handles...
    */

   /**
    * @class MyComponent
    * @brief Handles specific functionality in the accelerator.
    *
    * MyComponent is responsible for...
    *
    * @see RelatedClass
    */

Python Documentation (Docstrings)
---------------------------------

Use Google-style docstrings for all:

- Modules
- Classes
- Methods (including ``__init__``)
- Functions
- Module-level variables

Shell Script Headers
--------------------

.. code-block:: bash

   #!/bin/bash
   # =============================================================================
   # Script Name: script_name.sh
   # Description: One-line description
   # =============================================================================
   #
   # Purpose:
   #   Detailed description of what this script does.
   #
   # Usage:
   #   ./script_name.sh [options] <arguments>
   #
   # Options:
   #   -h, --help     Show this help message
   #
   # Examples:
   #   ./script_name.sh -v arg1
   # =============================================================================

Testing
=======

Before submitting:

1. Ensure the code compiles:

   .. code-block:: bash

      scons build/ARM/gem5.opt -j$(nproc)

2. Run existing benchmarks:

   .. code-block:: bash

      ./build/ARM/gem5.opt configs/SALAM/generated/fs_vadd.py

3. Test debug output:

   .. code-block:: bash

      ./build/ARM/gem5.opt --debug-flags=SALAMAll configs/...

Commit Messages
===============

Format:

.. code-block:: text

   component: Brief summary (50 chars max)

   Detailed explanation of what changed and why. Wrap at 72 characters.
   Include any relevant context or motivation.

   - Bullet points for multiple changes
   - Keep each point concise

Examples:

.. code-block:: text

   hwacc: Add cycle count tracking to LLVMInterface

   Track instruction execution cycles for performance analysis.
   Statistics are collected per-instruction-type and reported
   via the SALAMStats debug flag.

   - Add cycle counter to LLVMInterface
   - Update HWStatistics to collect cycle data
   - Add SALAMCycles debug flag

Pull Request Process
====================

1. **Update documentation** for any API changes
2. **Add tests** if applicable
3. **Describe changes** clearly in the PR description
4. **Reference issues** if fixing a bug (e.g., "Fixes #123")
5. **Request review** from maintainers

Building Documentation
======================

To build and preview documentation:

.. code-block:: bash

   # Install dependencies
   pip install -r docs/requirements.txt
   sudo apt install doxygen graphviz

   # Build documentation
   cd docs
   make all

   # Preview locally
   make serve

Questions?
==========

- Open an issue on GitHub
- Check existing documentation
- Review similar PRs for guidance
