idf_component_register(SRCS "main.c" "diagnostics.c" "ugen_profile.c" INCLUDE_DIRS "."
    REQUIRES instrument board_audio ui patches esp_timer esp_psram esp_app_format spi_flash)
