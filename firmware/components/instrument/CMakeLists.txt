idf_component_register(SRCS "instrument.c" "master_delay.c" "trace_probe.c" "output_volume.c" "remote_control.c" INCLUDE_DIRS "include" REQUIRES synthdef_engine LDFRAGMENTS "hot_code.lf")
target_compile_options(${COMPONENT_LIB} PRIVATE -std=c99 -fno-fast-math -ffp-contract=off)
