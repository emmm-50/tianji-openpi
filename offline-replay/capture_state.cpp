#include "management.hpp"
#include "monitored_lease.hpp"

#include <MarvinSDK.h>
#include <nlohmann/json.hpp>

#include <algorithm>
#include <array>
#include <charconv>
#include <chrono>
#include <fstream>
#include <iostream>
#include <string_view>
#include <thread>

using json = nlohmann::json;
using mios_marvin::MonitoredOwnerLease;

double mono() {
    return std::chrono::duration<double>(std::chrono::steady_clock::now().time_since_epoch()).count();
}

double wall() {
    return std::chrono::duration<double>(std::chrono::system_clock::now().time_since_epoch()).count();
}

void check_lease(MonitoredOwnerLease& lease) {
    if (!lease.valid(mono())) {
        throw std::runtime_error("LEASE_INVALID: " + lease.failure_reason());
    }
}

void capture_feedback(MonitoredOwnerLease& lease, json& out, bool retry_refresh = false) {
    check_lease(lease);
    DCSS frame{};
    double before = mono(), wall_before = wall();
    bool read = OnGetBuf(&frame);
    double after = mono(), wall_after = wall();
    json q_deg = json::array(), q_rad = json::array();
    for (float q : frame.m_Out[1].m_FB_Joint_Pos) {
        q_deg.push_back(q);
        q_rad.push_back(q * 3.14159265358979323846 / 180.0);
    }
    out["joint"] = {
        {"read_returned", read}, {"before_monotonic", before}, {"after_monotonic", after},
        {"before_unix", wall_before}, {"after_unix", wall_after}, {"arm", "B_assumed_right"},
        {"frame_serial", frame.m_Out[1].m_OutFrameSerial}, {"mode", frame.m_State[1].m_CurState},
        {"q_deg", q_deg}, {"q_rad", q_rad},
    };
    if (!read) {
        throw std::runtime_error("SDK_READ_FAILED");
    }

    auto request = mios_gripper::pack_sdk_terminal12(mios_gripper::refresh_request(1));
    std::array<unsigned char, 256> payload{};
    std::copy(request.begin(), request.end(), payload.begin());
    auto send_refresh = [&] {
        check_lease(lease);
        before = mono();
        wall_before = wall();
        bool sent = OnSetChDataB(payload.data(), 12, 1);
        after = mono();
        wall_after = wall();
        return json{
            {"request", request}, {"send_returned", sent},
            {"send_before_monotonic", before}, {"send_after_monotonic", after},
            {"send_before_unix", wall_before}, {"send_after_unix", wall_after},
        };
    };

    auto& gripper = out["gripper"];
    gripper = send_refresh();
    gripper.update({
        {"response", nullptr},
        {"encoding_ranges_source", "wsb_ws/records/acceptance/gripper_read_B_20261112_141302/result.json"},
        {"source_freshness_verified", false},
    });
    if (!gripper["send_returned"].get<bool>()) {
        throw std::runtime_error("REFRESH_SEND_FAILED");
    }

    double start = mono();
    double deadline = start + 0.4;
    while (mono() < deadline) {
        check_lease(lease);
        std::array<unsigned char, 256> raw{};
        long channel = 1;
        before = mono();
        wall_before = wall();
        long length = OnGetChDataB(raw.data(), &channel);
        after = mono();
        wall_after = wall();
        if (length < 0 || length > 256) {
            throw std::runtime_error("CHANNEL_READ_FAILED");
        }
        if (length > 0) {
            std::vector<unsigned char> bytes(raw.begin(), raw.begin() + length);
            gripper["response"] = {
                {"bytes", bytes}, {"channel", channel},
                {"before_monotonic", before}, {"after_monotonic", after},
                {"before_unix", wall_before}, {"after_unix", wall_after},
            };
            auto terminal = mios_gripper::unpack_sdk_terminal12(bytes, channel);
            auto feedback = mios_gripper::decode_feedback(terminal, mios_gripper::diagnostic_address(1));
            gripper["decoded"] = {
                {"can_id", terminal.can_id}, {"embedded_id", feedback.embedded_id},
                {"status", feedback.status}, {"q_rad", feedback.q_rad}, {"dq_rad_s", feedback.dq_rad_s},
                {"tau_nm", feedback.tau_nm}, {"mos_c", feedback.mos_c}, {"motor_c", feedback.motor_c},
            };
            return;
        }
        if (retry_refresh && mono() - start >= 0.05) {
            gripper["retry"] = send_refresh();
            retry_refresh = false;
        }
        std::this_thread::sleep_for(std::chrono::milliseconds(10));
    }
    out["error"] = "NO_GRIPPER_RESPONSE";
}

int main(int argc, char** argv) {
    if (argc == 1) {
        std::cout << "plan only: no SDK calls; --execute OUTPUT_JSON or --stream SECONDS\n";
        return 0;
    }
    if (argc != 3) {
        return 2;
    }
    const std::string_view mode = argv[1];
    const bool stream = mode == "--stream";
    int seconds = 15;
    if (stream) {
        const std::string_view duration = argv[2];
        const auto [end, error] = std::from_chars(duration.begin(), duration.end(), seconds);
        if (error != std::errc{} || end != duration.end() || seconds <= 0) {
            return 2;
        }
    } else if (mode != "--execute") {
        return 2;
    }

    const json observation_metadata = {{"source_time_available", false}, {"physical_mapping_verified", false}};
    json session = observation_metadata;
    session.update({{"sdk_connection_attempted", false}, {"release_attempted", false}, {"release_returned", false}});
    MonitoredOwnerLease lease(mono() + seconds);
    try {
        if (!lease.acquire(mono())) {
            throw std::runtime_error("EXCLUSIVE_HANDOFF_REQUIRED: " + lease.failure_reason());
        }
        check_lease(lease);
        session["sdk_connection_attempted"] = true;
        if (!OnLinkTo(6, 6, 7, 190)) {
            throw std::runtime_error("SDK_LINK_FAILED");
        }
        std::cout << "PI05_READY" << std::endl;

        if (stream) {
            std::string request;
            while (std::getline(std::cin, request)) {
                if (!request.empty()) {
                    throw std::runtime_error("EXPECTED_EMPTY_SAMPLE_REQUEST");
                }
                json sample = observation_metadata;
                try {
                    capture_feedback(lease, sample, true);
                } catch (const std::exception& error) {
                    sample["error"] = error.what();
                    std::cout << sample.dump() << std::endl;
                    throw;
                }
                std::cout << sample.dump() << std::endl;
            }
        } else {
            if (std::cin.get() != '\n') {
                throw std::runtime_error("COORDINATOR_CLOSED");
            }
            capture_feedback(lease, session);
        }
    } catch (const std::exception& error) {
        session["error"] = error.what();
    }
    if (session["sdk_connection_attempted"].get<bool>()) {
        session["release_attempted"] = true;
        session["release_returned"] = OnRelease();
    }
    if (stream) {
        std::cout << session.dump() << std::endl;
    } else {
        std::ofstream output(argv[2]);
        output << session.dump(2) << '\n';
        if (!output) {
            return 1;
        }
    }
    return !session.contains("error") && session["release_returned"].get<bool>() ? 0 : 1;
}
