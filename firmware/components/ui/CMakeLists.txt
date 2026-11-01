idf_component_register(SRCS "touch_ui.c" "touch_display.c" "sc_source.c" "sc_code_view.c" "code_font.c" INCLUDE_DIRS "include"
    REQUIRES instrument waveshare__esp32_s3_touch_amoled_1_8 esp_psram esp_lcd_touch esp_lcd)
