/*
 * Base64 encoding/decoding (RFC1341)
 * Copyright (c) 2005, Jouni Malinen <j@w1.fi>
 *
 * This software may be distributed under the terms of the BSD license.
 * See README for more details.
 */

#ifndef BASE64_H
#define BASE64_H

#ifdef __cplusplus
extern "C" {
#endif

#include <stddef.h>

void base64_encode(const unsigned char *src, size_t len, char *out);

size_t base64_decode(const unsigned char *src, size_t len, unsigned char *out);

#ifdef __cplusplus
}
#endif

#endif /* BASE64_H */
