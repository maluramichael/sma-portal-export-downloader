#!/bin/bash

# combine all exports to one big export
for file in temp/influx/*; do cat $file >>"temp/write_influx_via_curl.txt"; done

# create influx export
echo "# DDL" >"temp/influx_export.txt"
echo "CREATE DATABASE vault" >>"temp/influx_export.txt"
echo "" >>"temp/influx_export.txt"
echo "# DML" >>"temp/influx_export.txt"
echo "# CONTEXT-DATABASE: vault" >>"temp/influx_export.txt"
echo "" >>"temp/influx_export.txt"
for file in temp/influx/*; do cat $file >>"temp/influx_export.txt"; done
