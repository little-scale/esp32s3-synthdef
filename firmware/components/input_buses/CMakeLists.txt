idf_component_register(SRCS "input_buses.c" INCLUDE_DIRS "include")
target_compile_options(${COMPONENT_LIB} PRIVATE -Wall -Wextra -Werror -fno-fast-math -ffp-contract=off)
