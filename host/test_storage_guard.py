"""Compile and exercise the portable no-data-loss filesystem guard."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class StorageGuardTests(unittest.TestCase):
    def test_entire_region_and_read_failures(self):
        source = r'''
#include "storage_guard.h"
#include <assert.h>
#include <string.h>
static unsigned char flash[8193];
static size_t fail=SIZE_MAX, calls;
static bool read_bytes(void *ctx,size_t at,void *out,size_t n) {
    (void)ctx;++calls;if(at==fail)return false;
    assert(at<=sizeof flash && n<=sizeof flash-at);
    memcpy(out,flash+at,n);return true;
}
int main(void) {
    unsigned char scratch[4096];memset(flash,255,sizeof flash);
    assert(patch_storage_erased(read_bytes,0,sizeof flash,scratch,sizeof scratch));
    assert(calls==3);
    size_t offsets[]={0,4095,4096,8192};
    for(size_t i=0;i<sizeof offsets/sizeof offsets[0];++i){
        flash[offsets[i]]=0;
        assert(!patch_storage_erased(read_bytes,0,sizeof flash,scratch,sizeof scratch));
        flash[offsets[i]]=255;
    }
    fail=4096;
    assert(!patch_storage_erased(read_bytes,0,sizeof flash,scratch,sizeof scratch));
    assert(!patch_storage_erased(0,0,sizeof flash,scratch,sizeof scratch));
    assert(!patch_storage_erased(read_bytes,0,0,scratch,sizeof scratch));
    assert(!patch_storage_erased(read_bytes,0,sizeof flash,0,sizeof scratch));
    assert(!patch_storage_erased(read_bytes,0,sizeof flash,scratch,0));
    return 0;
}
'''
        compiler = shutil.which('cc')
        self.assertIsNotNone(compiler)
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder); (path/'guard.c').write_text(source)
            subprocess.run([compiler,'-std=c99','-Wall','-Wextra','-Werror',
                            '-I'+str(ROOT/'firmware/components/patches/include'),
                            str(path/'guard.c'),'-o',str(path/'guard')],check=True,capture_output=True)
            subprocess.run([str(path/'guard')],check=True,capture_output=True)


if __name__ == '__main__': unittest.main()
