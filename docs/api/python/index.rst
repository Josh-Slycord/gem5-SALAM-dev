.. _python-api:

=======================
Python SimObject source
=======================

The files below declare gem5-SALAM SimObjects and their configurable
parameters. They are included directly from the source tree: a standalone
documentation build does not import gem5's embedded ``m5`` runtime, and does
not claim to document every Python module or GUI component.

CommInterface
=============

.. literalinclude:: ../../../src/hwacc/CommInterface.py
   :language: python
   :linenos:

LLVMInterface
=============

.. literalinclude:: ../../../src/hwacc/LLVMInterface.py
   :language: python
   :linenos:

AccCluster
==========

.. literalinclude:: ../../../src/hwacc/AccCluster.py
   :language: python
   :linenos:

ScratchpadMemory
================

.. literalinclude:: ../../../src/hwacc/ScratchpadMemory.py
   :language: python
   :linenos:

RegisterBank
============

.. literalinclude:: ../../../src/hwacc/RegisterBank.py
   :language: python
   :linenos:

NoncoherentDma
==============

.. literalinclude:: ../../../src/hwacc/NoncoherentDma.py
   :language: python
   :linenos:

StreamDma
=========

.. literalinclude:: ../../../src/hwacc/StreamDma.py
   :language: python
   :linenos:

StreamBuffer
============

.. literalinclude:: ../../../src/hwacc/StreamBuffer.py
   :language: python
   :linenos:
