# Building gem5-SALAM on Ubuntu 24.04

## Overview

Ubuntu 24.04 ships with Python 3.12, which has several breaking changes that affect gem5-SALAM's build system. This document explains how to successfully build on Ubuntu 24.04.

## The Problem

Python 3.12 introduced changes that break gem5's SCons-based build:

1. **Import mechanism changes**:  deprecated in favor of 
2. **PLY regex compatibility**: Global flags must be at start of expression
3. **Module removal**:  module removed (use )

## Solution: Use Python 3.10

Ubuntu 24.04 can have multiple Python versions installed. Use Python 3.10 for building:

### 1. Install Python 3.10 (if not present)



### 2. Install SCons for Python 3.10



### 3. Install pybind11



### 4. Build with Python 3.10



## Verified Configurations

| Ubuntu | Python | SCons | GCC | Status |
|--------|--------|-------|-----|--------|
| 20.04 | 3.8 | 3.1.2 | 9.x | ✅ Works |
| 24.04 | 3.10 | 4.0.1 | 13.x | ✅ Works |
| 24.04 | 3.12 | 4.x | 13.x | ❌ Requires patches |

## Notes

- The embedded Python version in gem5 will still be detected as the system default (3.12), but this only affects runtime Python embedding, not the build process
- Build time is approximately 20-40 minutes on a 24-core system with 
- The resulting binary is ~765 MB for ARM architecture

## Alternative: Patching for Python 3.12

If you must use Python 3.12, the following files need patches:

1.  - Add  method to  class
2.  - Guard  import with try/except
3.  - Catch  for 
4.  - Fix PLY regex patterns for 3.11+ compatibility

These patches are complex and may introduce subtle issues. Using Python 3.10 is recommended.

---

*Document created: 2026-01-09*
*Tested on: Ubuntu 24.04.1 LTS, gem5-SALAM commit ebc07e95d*
