if("$ENV{SYNTHDEF_BOARD}" STREQUAL "voice_pe")
    idf_component_register(SRCS "headless_io_voice_pe.c" "voice_pe_leds.c" "voice_pe_grove.c"
        "../../../ports/voice_pe/main/voice_pe_controls.c" "../../../ports/voice_pe/main/voice_pe_dlight.c"
        INCLUDE_DIRS "include" "../../../ports/voice_pe/main"
        REQUIRES esp_driver_gpio esp_driver_pcnt esp_driver_rmt esp_driver_i2c esp_timer)
else()
    idf_component_register(SRCS "headless_io.c" INCLUDE_DIRS "include" REQUIRES esp_driver_gpio esp_adc esp_timer)
endif()
