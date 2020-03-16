#!/usr/bin/env bash
set -o errexit
set -o pipefail
set -o nounset

DATE=$(date +%y%m%d)

REPORTS="ONLINE5M"
DATA_DIR="data"
TMP_DIR="/tmp/sma"
TODAY_ZIP="$DATA_DIR/$REPORTS/DA$DATE.ZIP"

usage() {
  echo "Usage: $0 [-r REPORTS]" 1>&2
}

exit_abnormal() {
  usage
  exit 1
}

print_env() {
  echo "REPORTS=${REPORTS}"
  echo "DATA_DIR=${DATA_DIR}"
  echo "TMP_DIR=${TMP_DIR}"
}

while getopts "r:" options; do
  case "${options}" in
  r) REPORTS=${OPTARG} ;;
  :)
    echo "Error: -${OPTARG} requires an argument."
    exit_abnormal
    ;;
  *) exit_abnormal ;;
  esac
done

# extract downloaded zip files and merge the content to a single csv file
extract_zip_and_create_csv_and_export() {
  ZIP=$1
  FILENAME_WITH_EXT=$(basename -- "$ZIP")
  NAME="${FILENAME_WITH_EXT%.*}"
  DESTINATION="$TMP_DIR/$NAME"
  CVS_FILE="$DESTINATION/$NAME.csv"
  INFLUX_FILE="$DESTINATION/$NAME.influx"

  rm -r "${DESTINATION:?}"/*
  mkdir -p "$DESTINATION"

  echo "Extract $NAME"

  unzip -qo "$ZIP" -d "$DESTINATION"

  content=""
  for csv in "$DESTINATION"/*; do
    csv_content=$(sed -e '1,8d' -e '$ d' "$csv")
    if [ -n "$csv_content" ]; then
      content="${content}\\n${csv_content}"
    fi
  done

  rm -r "${DESTINATION:?}"/*

  if [[ ! -z $content ]]; then
    echo "$content" >"$CVS_FILE"

    while read -r l; do
      line=$(echo "$l" | sed -e 's/\r//g' | sed -e 's/\n//g')

      datetime=$(cut -d',' -f1 <<<"$line")
      time=$(echo "$datetime" | awk '{split($0, a, " "); print a[2]}')
      datetime=$(echo "$datetime" | awk '{split($0, a, " "); print a[1]}')
      datetime=$(echo "$datetime" | awk '{split($0, a, "."); print a[3]"/"a[2]"/"a[1]}')
      datetime="$datetime $time"
      datetime=$(echo $datetime | sed -e 's/\\//g' | sed -e 's/n//g')

      min=$(cut -d',' -f2 <<<"$line")
      avg=$(cut -d',' -f3 <<<"$line")
      max=$(cut -d',' -f4 <<<"$line")

      ts=""
      if [[ "$OSTYPE" == "darwin"* ]]; then
        ts=$(date -j -f "%Y/%m/%d %H:%M:%S" "$datetime" "+%s")
      elif [[ "$OSTYPE" == "linux-gnu" ]]; then
        ts=$(date -d "$datetime" "+%s")
      else
        exit 1
      fi

      if [[ ! -z $ts ]] && [[ ! -z $min ]] && [[ ! -z $avg ]] && [[ ! -z $max ]]; then
        ts="${ts}000000000"
        echo "power,type=production,source=pv min=$min,avg=$avg,max=$max $ts" >>"$INFLUX_FILE"
      fi
    done <<<"$content"
  fi
}

# export latest zip file
if [[ -f $TODAY_ZIP ]]; then
  if extract_zip_and_create_csv_and_export "$TODAY_ZIP"; then
    rm "$TODAY_ZIP"
  fi
fi

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
