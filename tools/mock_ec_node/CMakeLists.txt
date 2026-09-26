cmake_minimum_required(VERSION 3.10)
project(mock_ec_node)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# Linux-only project
if(NOT UNIX)
    message(FATAL_ERROR "This project requires Linux with SocketCAN support")
endif()

add_executable(mock_ec_node main.cpp)

# Warnings
target_compile_options(mock_ec_node PRIVATE
    -Wall
    -Wextra
    -Wpedantic
)

# Math library for sin/cos
target_link_libraries(mock_ec_node PRIVATE m)
