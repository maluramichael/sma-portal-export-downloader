#!/bin/bash

# send export to influx
curl -i -XPOST 'http://192.168.178.100:8086/write?db=vault&time_precision=s' --data-binary @temp/write_influx_via_curl.txt
