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
PORTAL="https://YOUR_SMA_ADDRESS" REPORTS="/DIAGNOSE/ONLINE5M/" GROUP=istl PASS=1111 ./download_files.sh
# The script now downloads, unzips and creates an export file for you

# you can now import the export.txt file into your influx instance like this
influx -import -path=export.txt -precision=s
```

## Todo
* Fix the bash script. Right now it only works with preloaded zip files and does not actually download the latest files from the portal.
