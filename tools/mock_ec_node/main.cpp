#include <iostream>
#include <cstring>
#include <cstdint>
#include <cmath>
#include <chrono>
#include <thread>
#include <string>
#include <unistd.h>
#include <sys/socket.h>
#include <sys/ioctl.h>
#include <net/if.h>
#include <linux/can.h>
#include <linux/can/raw.h>

// Protocol constants from tongji_sentry.yaml
constexpr uint32_t CAN_ID_QUATERNION = 0x01;
constexpr uint32_t CAN_ID_ROBOT_STATE = 0x110;
constexpr uint32_t CAN_ID_UNKNOWN = 0x999;

constexpr int QUATERNION_HZ = 100;
constexpr int ROBOT_STATE_HZ = 20;

enum class Mode {
    NORMAL,
    INVALID_ENUM,
    INVALID_QUATERNION,
    UNKNOWN_ID
};

// Big-endian int16 encoding (matching Python encoder)
void encode_int16_be(uint8_t* buf, int offset, int16_t value) {
    buf[offset] = (value >> 8) & 0xFF;
    buf[offset + 1] = value & 0xFF;
}

// Create quaternion message (CAN 0x01, DLC 8)
// Fields: x, y, z, w (int16 big-endian, scale 0.0001)
can_frame make_quaternion_frame(double t, Mode mode) {
    can_frame frame;
    std::memset(&frame, 0, sizeof(frame));

    frame.can_id = CAN_ID_QUATERNION;
    frame.can_dlc = 8;

    double x, y, z, w;

    if (mode == Mode::INVALID_QUATERNION) {
        // Obviously non-normalized quaternion
        x = 0.9;
        y = 0.9;
        z = 0.9;
        w = 0.9;  // norm = sqrt(4*0.81) = 1.8, far from 1.0
    } else {
        // Valid quaternion rotating around Z-axis
        double angle = t * 0.5;  // Slow rotation
        x = 0.0;
        y = 0.0;
        z = std::sin(angle / 2.0);
        w = std::cos(angle / 2.0);
    }

    // Scale and encode as int16 big-endian
    int16_t x_raw = static_cast<int16_t>(x * 10000.0);
    int16_t y_raw = static_cast<int16_t>(y * 10000.0);
    int16_t z_raw = static_cast<int16_t>(z * 10000.0);
    int16_t w_raw = static_cast<int16_t>(w * 10000.0);

    encode_int16_be(frame.data, 0, x_raw);
    encode_int16_be(frame.data, 2, y_raw);
    encode_int16_be(frame.data, 4, z_raw);
    encode_int16_be(frame.data, 6, w_raw);

    return frame;
}

// Create robot_state message (CAN 0x110, DLC 8)
// Fields: bullet_speed (int16), mode (uint8), shoot_mode (uint8), ft_angle (int16), unused (2 bytes)
can_frame make_robot_state_frame(double t, Mode mode) {
    can_frame frame;
    std::memset(&frame, 0, sizeof(frame));

    frame.can_id = CAN_ID_ROBOT_STATE;
    frame.can_dlc = 8;

    // bullet_speed: 10-30 m/s sinusoidal variation
    double bullet_speed = 20.0 + 10.0 * std::sin(t * 0.3);
    int16_t bullet_speed_raw = static_cast<int16_t>(bullet_speed * 100.0);
    encode_int16_be(frame.data, 0, bullet_speed_raw);

    // mode: cycle through valid enums (0-4) unless invalid_enum
    uint8_t mode_val;
    if (mode == Mode::INVALID_ENUM) {
        mode_val = 99;  // Invalid enum value
    } else {
        mode_val = static_cast<uint8_t>(static_cast<int>(t) % 5);
    }
    frame.data[2] = mode_val;

    // shoot_mode: cycle through 0, 1, 2
    uint8_t shoot_mode_val = static_cast<uint8_t>(static_cast<int>(t * 0.5) % 3);
    frame.data[3] = shoot_mode_val;

    // ft_angle: -π to π sinusoidal variation
    double ft_angle = M_PI * std::sin(t * 0.2);
    int16_t ft_angle_raw = static_cast<int16_t>(ft_angle * 10000.0);
    encode_int16_be(frame.data, 4, ft_angle_raw);

    // Bytes 6-7: unused (already zero from memset)

    return frame;
}

// Create unknown ID message for testing
can_frame make_unknown_frame(double t) {
    can_frame frame;
    std::memset(&frame, 0, sizeof(frame));

    frame.can_id = CAN_ID_UNKNOWN;
    frame.can_dlc = 8;

    // Fill with recognizable pattern
    for (int i = 0; i < 8; i++) {
        frame.data[i] = static_cast<uint8_t>((static_cast<int>(t * 10) + i) % 256);
    }

    return frame;
}

int main(int argc, char* argv[]) {
    if (argc != 3) {
        std::cerr << "Usage: " << argv[0] << " <interface> <mode>\n";
        std::cerr << "Modes:\n";
        std::cerr << "  normal             - Send valid quaternion and robot_state\n";
        std::cerr << "  invalid_enum       - Send invalid mode enum in robot_state\n";
        std::cerr << "  invalid_quaternion - Send non-normalized quaternion\n";
        std::cerr << "  unknown_id         - Periodically send unknown CAN ID 0x999\n";
        return 1;
    }

    const char* interface = argv[1];
    std::string mode_str = argv[2];

    Mode mode;
    if (mode_str == "normal") {
        mode = Mode::NORMAL;
    } else if (mode_str == "invalid_enum") {
        mode = Mode::INVALID_ENUM;
    } else if (mode_str == "invalid_quaternion") {
        mode = Mode::INVALID_QUATERNION;
    } else if (mode_str == "unknown_id") {
        mode = Mode::UNKNOWN_ID;
    } else {
        std::cerr << "Unknown mode: " << mode_str << "\n";
        return 1;
    }

    // Create SocketCAN socket
    int sock = socket(PF_CAN, SOCK_RAW, CAN_RAW);
    if (sock < 0) {
        std::cerr << "Error: Failed to create socket\n";
        return 1;
    }

    // Get interface index
    struct ifreq ifr;
    std::strncpy(ifr.ifr_name, interface, IFNAMSIZ - 1);
    ifr.ifr_name[IFNAMSIZ - 1] = '\0';

    if (ioctl(sock, SIOCGIFINDEX, &ifr) < 0) {
        std::cerr << "Error: Interface " << interface << " not found\n";
        close(sock);
        return 1;
    }

    // Bind socket to CAN interface
    struct sockaddr_can addr;
    std::memset(&addr, 0, sizeof(addr));
    addr.can_family = AF_CAN;
    addr.can_ifindex = ifr.ifr_ifindex;

    if (bind(sock, reinterpret_cast<struct sockaddr*>(&addr), sizeof(addr)) < 0) {
        std::cerr << "Error: Failed to bind to " << interface << "\n";
        close(sock);
        return 1;
    }

    std::cout << "Mock EC Node started on " << interface << " in mode: " << mode_str << "\n";
    std::cout << "Press Ctrl+C to stop\n";

    // Timing control
    auto start_time = std::chrono::steady_clock::now();
    int quat_counter = 0;
    int state_counter = 0;
    int unknown_counter = 0;

    while (true) {
        auto now = std::chrono::steady_clock::now();
        double t = std::chrono::duration<double>(now - start_time).count();

        // Quaternion at 100 Hz (every 10ms)
        if (quat_counter * 10 <= static_cast<int>(t * 1000)) {
            can_frame frame = make_quaternion_frame(t, mode);
            if (write(sock, &frame, sizeof(frame)) != sizeof(frame)) {
                std::cerr << "Warning: Failed to send quaternion frame\n";
            }
            quat_counter++;
        }

        // Robot state at 20 Hz (every 50ms)
        if (state_counter * 50 <= static_cast<int>(t * 1000)) {
            can_frame frame = make_robot_state_frame(t, mode);
            if (write(sock, &frame, sizeof(frame)) != sizeof(frame)) {
                std::cerr << "Warning: Failed to send robot_state frame\n";
            }
            state_counter++;
        }

        // Unknown ID at 10 Hz (every 100ms) in unknown_id mode
        if (mode == Mode::UNKNOWN_ID && unknown_counter * 100 <= static_cast<int>(t * 1000)) {
            can_frame frame = make_unknown_frame(t);
            if (write(sock, &frame, sizeof(frame)) != sizeof(frame)) {
                std::cerr << "Warning: Failed to send unknown ID frame\n";
            }
            unknown_counter++;
        }

        // Sleep for 1ms to avoid busy-waiting
        std::this_thread::sleep_for(std::chrono::milliseconds(1));
    }

    close(sock);
    return 0;
}
