# sma-portal-export-downloader

Download every export from the SMA Sunny Portal

The following devices are tested:
* Sunny Tripower 6.0 (2.13.33.R)

## Getting started on linux or mac

Install the following packages

```
apt install jq zip unzip curl
```

or on mac

```
brew install jq zip unzip curl
```

## Use the bash script

```shell script
export PORTAL="https://YOUR_SMA_ADDRESS"
export REPORTS="/DIAGNOSE/ONLINE5M/"
export GROUP=istl
export PASS=1111
./download_files.sh
./extract_zip_files_and_create_export_files.sh
./combine_export_files.sh
./send_export_to_influx.sh
# The script now downloads, unzips and creates an export file for you

# you can now import the export.txt file into your influx instance like this
influx -import -path=temp/influx_export.txt -precision=s
```

## My cronjob

`0 * * * * cd $HOME/sma && . $HOME/.profile && ./download_files.sh && extract_zip_files_and_create_export_files.sh && ./combine_export_files.sh && ./send_export_to_influx.sh`
