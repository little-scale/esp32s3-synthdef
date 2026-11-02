set(APP_REQUIRES instrument board_audio patches esp_timer esp_psram esp_app_format spi_flash)
if(NOT "$ENV{SYNTHDEF_BOARD}" STREQUAL "xiao")
    list(APPEND APP_REQUIRES ui)
else()
    list(APPEND APP_REQUIRES headless_io)
endif()
idf_component_register(SRCS "main.c" "diagnostics.c" "ugen_profile.c" INCLUDE_DIRS "."
    REQUIRES ${APP_REQUIRES})
