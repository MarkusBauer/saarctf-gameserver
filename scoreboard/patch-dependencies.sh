#!/usr/bin/env bash

set -e

grep -q 'initStorageEvent' 'node_modules/ngx-store/lib/utility/storage/storage-event.d.ts' || \
  sed -i '/constructor/a initStorageEvent(type: string, bubbles?: boolean, cancelable?: boolean, key?: string | null, oldValue?: string | null, newValue?: string | null, url?: string | URL, storageArea?: Storage | null): void;' 'node_modules/ngx-store/lib/utility/storage/storage-event.d.ts'
