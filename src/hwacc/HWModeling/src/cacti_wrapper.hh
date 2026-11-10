#ifndef __HWMODEL_CACTI_WRAPPER_HH__
#define __HWMODEL_CACTI_WRAPPER_HH__

/**
 * @file
 * @brief C++ wrapper interface for CACTI cache and memory modeling.
 */

#include "../../../../ext/mcpat/cacti/cacti_interface.h"


uca_org_t cactiWrapper(unsigned num_of_bytes, unsigned wordsize, unsigned num_ports, int cache_type);

#endif //__HWMODEL_CACTI_WRAPPER_HH__
