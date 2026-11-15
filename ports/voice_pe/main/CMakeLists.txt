configure_file("${CMAKE_CURRENT_LIST_DIR}/../../../examples/gated-sine.scsyndef"
               "${CMAKE_CURRENT_BINARY_DIR}/probe.scsyndef" COPYONLY)
idf_component_register(SRCS "main.c" "voice_pe_board.c" "voice_pe_format.c" "voice_pe_probe.c" "voice_pe_survey.c" "voice_pe_silent_dma.c" "voice_pe_codec_sequence.c" "voice_pe_codec.c" "voice_pe_test_tone.c"
    INCLUDE_DIRS "."
    REQUIRES synthdef_engine esp_driver_gpio esp_driver_i2s esp_psram spi_flash esp_timer esp_driver_i2c esp_driver_pcnt esp_driver_usb_serial_jtag esp_hw_support vfs)
target_add_binary_data(${COMPONENT_LIB} "${CMAKE_CURRENT_BINARY_DIR}/probe.scsyndef" BINARY)
target_compile_options(${COMPONENT_LIB} PRIVATE -Wall -Wextra -Werror -fno-fast-math -ffp-contract=off)
