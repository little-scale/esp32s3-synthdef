cmake_minimum_required(VERSION 3.16)
set(COMPONENTS main)
include($ENV{IDF_PATH}/tools/cmake/project.cmake)
project(waveshare_synthdef VERSION 0.1.0)
if(CONFIG_SYNTHDEF_HEADLESS AND NOT "$ENV{SYNTHDEF_BOARD}" STREQUAL "xiao")
    message(FATAL_ERROR "Use host/xiao.sh for the headless target")
endif()
if("$ENV{SYNTHDEF_BOARD}" STREQUAL "xiao" AND NOT CONFIG_SYNTHDEF_HEADLESS)
    message(FATAL_ERROR "The XIAO build requires CONFIG_SYNTHDEF_HEADLESS=y and a separate sdkconfig")
endif()
add_custom_target(check_project_metadata ALL
    COMMAND "${PYTHON}" "${CMAKE_CURRENT_LIST_DIR}/../host/prepare.py" --check
    WORKING_DIRECTORY "${CMAKE_CURRENT_LIST_DIR}/..")
