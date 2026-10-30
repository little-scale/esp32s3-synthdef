cmake_minimum_required(VERSION 3.16)
include($ENV{IDF_PATH}/tools/cmake/project.cmake)
project(waveshare_synthdef VERSION 0.1.0)
add_custom_target(check_project_metadata ALL
    COMMAND "${PYTHON}" "${CMAKE_CURRENT_LIST_DIR}/../host/prepare.py" --check
    WORKING_DIRECTORY "${CMAKE_CURRENT_LIST_DIR}/..")
