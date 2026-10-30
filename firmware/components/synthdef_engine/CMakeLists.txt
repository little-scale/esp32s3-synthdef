set(ENGINE "${CMAKE_CURRENT_LIST_DIR}/../../../upstream/fm1-synthdef/synthdef-engine/src")
idf_component_register(SRCS "${ENGINE}/fm_load.c" "${ENGINE}/fm_render.c"
                       INCLUDE_DIRS "${ENGINE}" LDFRAGMENTS "hot_data.lf")
target_compile_options(${COMPONENT_LIB} PRIVATE -std=c99 -fno-fast-math -ffp-contract=off)
# The pinned source is tested with Clang. GCC 14 diagnoses its compact formatting,
# array spelling, and parser-validated arithmetic input counts. Keep diagnostics
# visible without making these three upstream warning classes fatal to this port.
target_compile_options(${COMPONENT_LIB} PRIVATE -Wno-error=misleading-indentation
    -Wno-error=array-parameter -Wno-error=maybe-uninitialized)
