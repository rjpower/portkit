#ifndef LIBXML2_COMPAT_H
#define LIBXML2_COMPAT_H

/* Compatibility wrapper to ensure all necessary system headers are included */

/* Include system string.h FIRST to avoid conflicts with libxml2's private/string.h */
#include <string.h>
#include <stdio.h>
#include <stdlib.h>
#include <limits.h>
#include <stdint.h>

/* Ensure we have the main libxml2 config */
#ifdef HAVE_CONFIG_H
#include "config.h"
#endif

/* Platform-specific includes */
#ifdef _WIN32
#include <windows.h>
#include <io.h>
#else
#include <unistd.h>
#include <sys/types.h>
#include <sys/stat.h>
#endif

/* Thread support */
#ifdef HAVE_PTHREAD_H
#include <pthread.h>
#endif

#endif /* LIBXML2_COMPAT_H */