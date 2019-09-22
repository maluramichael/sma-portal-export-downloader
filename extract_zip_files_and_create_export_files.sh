#!/bin/bash

if [ -z $REPORTS ]; then
  echo "REPORTS variable is missing"
  echo "Example:"
  echo "REPORTS=\"/DIAGNOSE/ONLINE5M/\""
  exit 1
fi

DATA_DIR="data$REPORTS"

mkdir -p temp/influx

# extract downloaded zip files and merge the content to a single csv file
extract_zip_and_create_csv_and_export() {
  zip=$1
  filename=$(basename -- "$zip")
  name="${filename%.*}"
  mkdir -p "temp/$name"

  echo "Extract $name"
  unzip -qo "$zip" -d "temp/$name"
  content=""
  for csv in temp/"$name"/*; do
    csv_content=$(sed -e '1,8d' -e '$ d' "$csv")
    if [ -n "$csv_content" ]; then
      content="${content}\n${csv_content}"
    fi
  done

  while read -r l; do
    line=$(echo $l | sed -e 's/\r//g' | sed -e 's/\n//g')

    datetime=$(cut -d',' -f1 <<<"$line")
    time=$(echo "$datetime" | awk '{split($0, a, " "); print a[2]}')
    datetime=$(echo "$datetime" | awk '{split($0, a, " "); print a[1]}')
    datetime=$(echo "$datetime" | awk '{split($0, a, "."); print a[3]"/"a[2]"/"a[1]}')
    datetime="$datetime $time"
    datetime=$(echo $datetime | sed -e 's/\\//g' | sed -e 's/n//g')

    min=$(cut -d',' -f2 <<<"$line")
    avg=$(cut -d',' -f3 <<<"$line")
    max=$(cut -d',' -f4 <<<"$line")

    if [ -n "$avg" ]; then
      ts=""
      if [[ "$OSTYPE" == "darwin"* ]]; then
        ts=$(date -j -f "%Y/%m/%d %H:%M:%S" "$datetime" "+%s")
      elif [[ "$OSTYPE" == "linux-gnu" ]]; then
        ts=$(date -d "$datetime" "+%s")
      else
        exit 1
      fi

      ts="${ts}000000000"
      echo "power,type=production,source=pv min=$min,avg=$avg,max=$max $ts" >>"temp/influx/$name.txt"
    fi
  done <<<"$content"
  echo "$content" >"temp/$name.csv"
}

# export latest zip file
extract_zip_and_create_csv_and_export "${DATA_DIR}today.ZIP"
rm "${DATA_DIR}today.ZIP"

# export everything parallel
# N=8
# (
#   for zip in $DATA_DIR*.ZIP; do
#     ((i = i % N))
#     ((i++ == 0)) && wait
#     extract_zip_and_create_csv_and_export "$zip" &
#   done
# )

# export everything in series
# for zip in $DATA_DIR*.ZIP; do
#   extract_zip_and_create_csv_and_export "$zip"
# done
