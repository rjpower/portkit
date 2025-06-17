#include <stdio.h>
#include <stdlib.h>
#include "src/zopfli/deflate.h"

int main() {
    ZopfliOptions options;
    ZopfliInitOptions(&options);
    options.verbose = 1;
    options.numiterations = 1;
    options.blocksplittingmax = 3;
    
    // Simplified test input based on the failing case
    unsigned char input[] = {189, 189, 43, 189, 189, 77, 77, 77, 77, 0, 77, 189, 77, 77, 77, 77, 0, 77, 255, 189, 189, 255, 255, 255, 189, 121, 121, 121, 121, 121, 121, 121, 121, 255, 255, 255, 255, 255, 255, 255, 255, 255, 255, 255, 255, 189, 189, 255, 189, 189, 189, 189, 121, 121, 121, 121, 121, 121, 121, 121, 121, 249, 83, 83, 81, 51};
    unsigned char* out = NULL;
    size_t outsize = 0;
    unsigned char bp = 0;
    
    printf("Testing C ZopfliDeflatePart...\n");
    ZopfliDeflatePart(&options, 2, 1, input, 0, 66, &bp, &out, &outsize);
    printf("C: bp=%d, outsize=%zu\n", bp, outsize);
    
    if (out && outsize > 0) {
        printf("C output bytes: ");
        for (size_t i = 0; i < outsize && i < 10; i++) {
            printf("%d ", out[i]);
        }
        printf("\n");
    }
    
    if (out) free(out);
    return 0;
}