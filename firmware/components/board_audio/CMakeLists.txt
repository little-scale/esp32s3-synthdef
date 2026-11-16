if("$ENV{SYNTHDEF_BOARD}" STREQUAL "voice_pe")
    set(VPE "${CMAKE_CURRENT_LIST_DIR}/../../../ports/voice_pe/main")
    idf_component_register(SRCS "board_audio_voice_pe.c" "${VPE}/voice_pe_board.c"
        "${VPE}/voice_pe_format.c" "${VPE}/voice_pe_survey.c" "${VPE}/voice_pe_codec.c"
        "${VPE}/voice_pe_codec_sequence.c" "${VPE}/voice_pe_resampler.c"
        INCLUDE_DIRS "include" PRIV_INCLUDE_DIRS "${VPE}"
        REQUIRES esp_driver_i2s esp_driver_gpio esp_driver_i2c esp_driver_pcnt esp_psram esp_timer)
elseif("$ENV{SYNTHDEF_BOARD}" STREQUAL "xiao")
    idf_component_register(SRCS "board_audio_i2s.c" INCLUDE_DIRS "include"
        REQUIRES esp_driver_i2s esp_driver_gpio esp_psram instrument)
else()
    idf_component_register(SRCS "board_audio.c" INCLUDE_DIRS "include"
        REQUIRES waveshare__esp32_s3_touch_amoled_1_8 esp_codec_dev esp_driver_i2s esp_driver_gpio)
endif()
