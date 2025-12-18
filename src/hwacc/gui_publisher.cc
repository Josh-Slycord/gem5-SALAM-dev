/**
 * @file gui_publisher.cc
 * @brief Implementation of ZeroMQ publisher for real-time GUI monitoring.
 */

#include "hwacc/gui_publisher.hh"

#include <chrono>
#include <sstream>
#include <iostream>
#include <memory>

// Conditionally include ZeroMQ
#ifdef HAVE_ZEROMQ
#include <zmq.hpp>
#endif

namespace gem5 {

// Pimpl implementation struct
struct GUIPublisherImpl {
#ifdef HAVE_ZEROMQ
    std::unique_ptr<zmq::context_t> context;
    std::unique_ptr<zmq::socket_t> socket;
#endif
};

// Global publisher instance
static std::unique_ptr<GUIPublisher> globalPublisher;

GUIPublisher::GUIPublisher(const std::string& addr, bool enable)
    : address(addr)
    , enabled(enable)
    , initialized(false)
    , impl(new GUIPublisherImpl())
    , lastPublishCycle(0)
    , publishInterval(100)  // Publish every 100 cycles by default
{
}

GUIPublisher::~GUIPublisher() {
    shutdown();
    delete impl;
}

bool GUIPublisher::initialize() {
#ifdef HAVE_ZEROMQ
    if (initialized || !enabled) {
        return initialized;
    }

    try {
        impl->context = std::make_unique<zmq::context_t>(1);
        impl->socket = std::make_unique<zmq::socket_t>(
            *impl->context, zmq::socket_type::pub);

        // Set socket options
        int linger = 0;
        impl->socket->setsockopt(ZMQ_LINGER, &linger, sizeof(linger));

        impl->socket->bind(address);
        initialized = true;

        std::cout << "GUI Publisher initialized on " << address << std::endl;
        return true;

    } catch (const zmq::error_t& e) {
        std::cerr << "Failed to initialize GUI Publisher: "
                  << e.what() << std::endl;
        initialized = false;
        return false;
    }
#else
    // ZeroMQ not available - silently disable
    enabled = false;
    return false;
#endif
}

void GUIPublisher::shutdown() {
#ifdef HAVE_ZEROMQ
    if (impl->socket) {
        impl->socket->close();
        impl->socket.reset();
    }
    if (impl->context) {
        impl->context->close();
        impl->context.reset();
    }
    initialized = false;
#endif
}

void GUIPublisher::sendMessage(const std::string& jsonMsg) {
#ifdef HAVE_ZEROMQ
    if (!isEnabled() || !impl->socket) {
        return;
    }

    try {
        zmq::message_t message(jsonMsg.size());
        memcpy(message.data(), jsonMsg.data(), jsonMsg.size());
        impl->socket->send(message, zmq::send_flags::dontwait);
    } catch (const zmq::error_t& e) {
        // Silently ignore send errors (no subscribers, etc.)
    }
#endif
}

double GUIPublisher::getCurrentTimestamp() {
    auto now = std::chrono::system_clock::now();
    auto duration = now.time_since_epoch();
    return std::chrono::duration<double>(duration).count();
}

void GUIPublisher::publishSimulationStart(const std::string& simName,
                                          const std::string& accelName) {
    if (!isEnabled()) return;

    std::ostringstream json;
    json << "{"
         << "\"type\":\"sim_start\","
         << "\"cycle\":0,"
         << "\"timestamp\":" << getCurrentTimestamp() << ","
         << "\"data\":{"
         << "\"sim_name\":\"" << simName << "\","
         << "\"accel_name\":\"" << accelName << "\""
         << "}"
         << "}";

    sendMessage(json.str());
}

void GUIPublisher::publishSimulationEnd(uint64_t totalCycles) {
    if (!isEnabled()) return;

    std::ostringstream json;
    json << "{"
         << "\"type\":\"sim_end\","
         << "\"cycle\":" << totalCycles << ","
         << "\"timestamp\":" << getCurrentTimestamp() << ","
         << "\"data\":{"
         << "\"total_cycles\":" << totalCycles
         << "}"
         << "}";

    sendMessage(json.str());
}

void GUIPublisher::publishCycleUpdate(uint64_t cycle) {
    if (!isEnabled()) return;

    // Rate limiting
    if (cycle - lastPublishCycle < publishInterval) {
        return;
    }
    lastPublishCycle = cycle;

    std::ostringstream json;
    json << "{"
         << "\"type\":\"cycle_update\","
         << "\"cycle\":" << cycle << ","
         << "\"timestamp\":" << getCurrentTimestamp() << ","
         << "\"data\":{}"
         << "}";

    sendMessage(json.str());
}

void GUIPublisher::publishQueueState(uint64_t cycle,
                                     int readQueueDepth,
                                     int writeQueueDepth,
                                     int computeQueueDepth) {
    if (!isEnabled()) return;

    std::ostringstream json;
    json << "{"
         << "\"type\":\"queue_state\","
         << "\"cycle\":" << cycle << ","
         << "\"timestamp\":" << getCurrentTimestamp() << ","
         << "\"data\":{"
         << "\"read_depth\":" << readQueueDepth << ","
         << "\"write_depth\":" << writeQueueDepth << ","
         << "\"compute_depth\":" << computeQueueDepth
         << "}"
         << "}";

    sendMessage(json.str());
}

void GUIPublisher::publishFUState(uint64_t cycle,
                                  const std::string& fuName,
                                  bool busy,
                                  double utilization) {
    if (!isEnabled()) return;

    std::ostringstream json;
    json << "{"
         << "\"type\":\"fu_state\","
         << "\"cycle\":" << cycle << ","
         << "\"timestamp\":" << getCurrentTimestamp() << ","
         << "\"data\":{"
         << "\"fu_name\":\"" << fuName << "\","
         << "\"busy\":" << (busy ? "true" : "false") << ","
         << "\"utilization\":" << utilization
         << "}"
         << "}";

    sendMessage(json.str());
}

void GUIPublisher::publishInstructionIssue(uint64_t cycle,
                                           int uid,
                                           const std::string& opcode,
                                           const std::string& fuType) {
    if (!isEnabled()) return;

    std::ostringstream json;
    json << "{"
         << "\"type\":\"instruction_issue\","
         << "\"cycle\":" << cycle << ","
         << "\"timestamp\":" << getCurrentTimestamp() << ","
         << "\"data\":{"
         << "\"uid\":" << uid << ","
         << "\"opcode\":\"" << opcode << "\","
         << "\"fu_type\":\"" << fuType << "\""
         << "}"
         << "}";

    sendMessage(json.str());
}

void GUIPublisher::publishInstructionComplete(uint64_t cycle, int uid) {
    if (!isEnabled()) return;

    std::ostringstream json;
    json << "{"
         << "\"type\":\"instruction_complete\","
         << "\"cycle\":" << cycle << ","
         << "\"timestamp\":" << getCurrentTimestamp() << ","
         << "\"data\":{"
         << "\"uid\":" << uid
         << "}"
         << "}";

    sendMessage(json.str());
}

void GUIPublisher::publishStallEvent(uint64_t cycle,
                                     int uid,
                                     const std::string& reason) {
    if (!isEnabled()) return;

    std::ostringstream json;
    json << "{"
         << "\"type\":\"stall_event\","
         << "\"cycle\":" << cycle << ","
         << "\"timestamp\":" << getCurrentTimestamp() << ","
         << "\"data\":{"
         << "\"uid\":" << uid << ","
         << "\"reason\":\"" << reason << "\""
         << "}"
         << "}";

    sendMessage(json.str());
}

void GUIPublisher::publishStatsUpdate(uint64_t cycle, const std::string& statsJson) {
    if (!isEnabled()) return;

    std::ostringstream json;
    json << "{"
         << "\"type\":\"stats_update\","
         << "\"cycle\":" << cycle << ","
         << "\"timestamp\":" << getCurrentTimestamp() << ","
         << "\"data\":" << statsJson
         << "}";

    sendMessage(json.str());
}

void GUIPublisher::publishHeartbeat() {
    if (!isEnabled()) return;

    std::ostringstream json;
    json << "{"
         << "\"type\":\"heartbeat\","
         << "\"cycle\":0,"
         << "\"timestamp\":" << getCurrentTimestamp() << ","
         << "\"data\":{}"
         << "}";

    sendMessage(json.str());
}

// Global instance management

GUIPublisher& getGUIPublisher() {
    if (!globalPublisher) {
        // Create with default disabled state if not initialized
        globalPublisher = std::make_unique<GUIPublisher>("tcp://*:5555", false);
    }
    return *globalPublisher;
}

void initGUIPublisher(const std::string& address, bool enabled) {
    globalPublisher = std::make_unique<GUIPublisher>(address, enabled);
    if (enabled) {
        globalPublisher->initialize();
    }
}

} // namespace gem5
