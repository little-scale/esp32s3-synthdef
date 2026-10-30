idf_component_register(SRCS "patch_format.c" "patch_service.c" INCLUDE_DIRS "include"
    REQUIRES instrument synthdef_engine esp_timer esp_psram spiffs nvs_flash mbedtls)
