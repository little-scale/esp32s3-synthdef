"""Check LVGL pool placement, repeated init ownership and allocation failures."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class UIPoolTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        directory = Path(cls.temp.name)
        (directory / 'esp_err.h').write_text('''#include <stdlib.h>
#define ESP_OK 0
#define ESP_ERR_NO_MEM 2
#define ESP_ERR_INVALID_SIZE 3
#define ESP_ERROR_CHECK(value) do { int error=(value); if(error) exit(error); } while(0)
''')
        (directory / 'esp_heap_caps.h').write_text('''#include <stddef.h>
#define MALLOC_CAP_SPIRAM 1
#define MALLOC_CAP_8BIT 2
void *heap_caps_malloc(size_t bytes, unsigned caps);
''')
        (directory / 'check.c').write_text('''#include <assert.h>
#include <stdlib.h>
#include <string.h>
#include "lvgl_psram_pool.h"
static unsigned calls;
static int fail;
void *heap_caps_malloc(size_t bytes, unsigned caps) {
    assert(bytes==65536 && caps==(MALLOC_CAP_SPIRAM|MALLOC_CAP_8BIT));
    ++calls;
    return fail ? NULL : malloc(bytes);
}
int main(int argc, char **argv) {
    assert(argc==2);
    fail=!strcmp(argv[1],"nomem");
    void *first=synthdef_lvgl_pool_alloc(65536);
    memset(first,0xa5,65536);
    for(unsigned i=0;i<100;++i) assert(synthdef_lvgl_pool_alloc(65536)==first);
    assert(calls==1 && ((unsigned char *)first)[65535]==0xa5);
    if(!strcmp(argv[1],"resize")) synthdef_lvgl_pool_alloc(32768);
    free(first);
    return 0;
}
''')
        cls.binary = directory / 'check'
        subprocess.run([shutil.which('cc') or 'cc', '-std=c99', '-Wall', '-Wextra',
                        '-Werror', '-I'+str(directory),
                        '-I'+str(ROOT/'firmware/components/ui/include'),
                        str(directory/'check.c'), '-o', str(cls.binary)], check=True)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_reinitialization_reuses_one_psram_pool(self):
        self.assertEqual(subprocess.run([str(self.binary), 'normal']).returncode, 0)

    def test_out_of_memory_fails_before_lvgl_uses_null(self):
        self.assertEqual(subprocess.run([str(self.binary), 'nomem']).returncode, 2)

    def test_changed_pool_size_is_rejected(self):
        self.assertEqual(subprocess.run([str(self.binary), 'resize']).returncode, 3)


if __name__ == '__main__':
    unittest.main()
