#include <stdio.h>
#include <stdlib.h>
#include "src/zopfli/deflate.h"

int main() {
    ZopfliOptions options;
    ZopfliInitOptions(&options);
    options.verbose = 1;
    
    unsigned char input[] = {99};
    unsigned char* out = NULL;
    size_t outsize = 0;
    unsigned char bp = 0;
    
    printf("Testing ZopfliDeflatePart with empty range...\n");
    ZopfliDeflatePart(&options, 1, 0, input, 0, 0, &bp, &out, &outsize);
    printf("Success\! outsize=%zu\n", outsize);
    
    if (out) free(out);
    return 0;
}
