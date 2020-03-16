#!/usr/bin/env bash
set -o errexit
set -o pipefail
set -o nounset

TMP_DIR="/tmp/sma"

# combine all exports to one big export
find $TMP_DIR -type f -iname "*.influx" -exec curl -i -XPOST 'http://192.168.178.2:8086/write?db=vault&time_precision=s' --data-binary @{} \;
find $TMP_DIR -type f -iname "*.influx" -delete
