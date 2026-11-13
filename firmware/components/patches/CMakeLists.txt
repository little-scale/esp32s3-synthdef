set(PATCH_REQUIRES instrument synthdef_engine board_audio esp_timer esp_psram spiffs nvs_flash mbedtls esp_wifi esp_netif esp_event esp_http_server json)
if("$ENV{SYNTHDEF_BOARD}" STREQUAL "xiao")
    list(APPEND PATCH_REQUIRES headless_io)
endif()
idf_component_register(SRCS "patch_format.c" "patch_service.c" "device_network.c" "pattern_service.c" INCLUDE_DIRS "include"
    REQUIRES ${PATCH_REQUIRES})
