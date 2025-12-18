/*
 * Copyright (c) 2024 gem5-SALAM Contributors
 * All rights reserved.
 *
 * SALAM Core Library - Main Header
 * Version: 3.0.0.pre[1.0.0]
 *
 * This header provides the complete SALAM core API for building
 * hardware accelerator simulations. The core library is simulator-
 * agnostic and can run on multiple backends (gem5, standalone, etc.).
 */

#ifndef __SALAM_SALAM_HH__
#define __SALAM_SALAM_HH__

// Core interfaces
#include "salam/simulation_context.hh"
#include "salam/hardware_component.hh"
#include "salam/memory_interface.hh"

// Version information
namespace salam {

constexpr const char* VERSION = "3.0.0.pre[1.0.0]";
constexpr int VERSION_MAJOR = 3;
constexpr int VERSION_MINOR = 0;
constexpr int VERSION_PATCH = 0;
constexpr const char* VERSION_STAGE = "pre";
constexpr const char* MODULE_VERSION = "1.0.0";

/**
 * Get the SALAM core library version string.
 */
inline const char* getVersion() {
    return VERSION;
}

} // namespace salam

#endif // __SALAM_SALAM_HH__
