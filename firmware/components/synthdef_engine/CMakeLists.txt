set(ORIGINAL_ENGINE "${CMAKE_CURRENT_LIST_DIR}/../../../upstream/fm1-synthdef/synthdef-engine/src")
set(PROFILE_SCRIPT "${CMAKE_CURRENT_LIST_DIR}/../../../host/engine_profile.py")
set(ENGINE "${CMAKE_CURRENT_BINARY_DIR}/target-profile/src")
file(GLOB ENGINE_INPUTS "${ORIGINAL_ENGINE}/*.c" "${ORIGINAL_ENGINE}/*.h" "${ORIGINAL_ENGINE}/*.inc")
set_property(DIRECTORY APPEND PROPERTY CMAKE_CONFIGURE_DEPENDS ${ENGINE_INPUTS} "${PROFILE_SCRIPT}")
set(ENGINE_PROFILE compact)
if(CONFIG_SYNTHDEF_FM1_COMPAT)
    set(ENGINE_PROFILE fm1)
endif()
execute_process(COMMAND "${PYTHON}" "${PROFILE_SCRIPT}" --profile "${ENGINE_PROFILE}" --output "${ENGINE}" RESULT_VARIABLE PROFILE_RESULT)
if(NOT PROFILE_RESULT EQUAL 0)
    message(FATAL_ERROR "Target engine capacity generation failed")
endif()
set(ENGINE_SOURCES "${ENGINE}/fm_load.c" "${ENGINE}/fm_render.c")
if(CONFIG_SYNTHDEF_DIAGNOSTICS)
    configure_file("${ENGINE}/fm_profile_render.inc" "${CMAKE_CURRENT_BINARY_DIR}/fm_profile_render.c" COPYONLY)
    list(APPEND ENGINE_SOURCES "${CMAKE_CURRENT_BINARY_DIR}/fm_profile_render.c")
endif()
idf_component_register(SRCS ${ENGINE_SOURCES}
                       INCLUDE_DIRS "${ENGINE}" PRIV_REQUIRES esp_hw_support LDFRAGMENTS "hot_data.lf")
target_compile_options(${COMPONENT_LIB} PRIVATE -std=c99 -fno-fast-math -ffp-contract=off)
# The pinned source is tested with Clang. GCC 14 diagnoses its compact formatting,
# array spelling, and parser-validated arithmetic input counts. Keep diagnostics
# visible without making these three upstream warning classes fatal to this port.
target_compile_options(${COMPONENT_LIB} PRIVATE -Wno-error=misleading-indentation
    -Wno-error=array-parameter -Wno-error=maybe-uninitialized)
