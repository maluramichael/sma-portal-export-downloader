#!/usr/bin/env bash
set -o errexit
set -o pipefail
set -o nounset

DATE=$(date +%Y%m%d)

PORTAL=""
REPORTS="ONLINE5M"
GROUP="istl"
PASS=""

DATA_DIR="data"
TMP_DIR="/tmp/sma"
SESSION_PATH="$TMP_DIR/session.txt"
SESSION=""

DOWNLOAD_LIVE=0
DOWNLOAD_ARCHIVE=0

# How to use
# PORTAL="https://YOUR_SMA_ADDRESS" REPORTS="ONLINE5M" GROUP=istl PASS=1111 ./download_files.sh

usage() {
  echo "Usage: $0 <-p PORTAL> [-r REPORTS] [-g GROPU] <-x PASSWORD>" 1>&2
}

exit_abnormal() {
  usage
  exit 1
}

print_env() {
  echo "PORTAL=${PORTAL}"
  echo "REPORTS=${REPORTS}"
  echo "GROUP=${GROUP}"
  echo "PASS=${PASS}"
  echo "DATA_DIR=${DATA_DIR}"
  echo "TMP_DIR=${TMP_DIR}"
  echo "SESSION_PATH=${SESSION_PATH}"
  echo "SESSION=${SESSION}"
}

login_session() {
  echo "Login $1 $2"
  result=$(curl -s -k -X POST -H "Content-Type: application/json" -d "{\"right\": \"$GROUP\", \"pass\": \"$PASS\"}" "$PORTAL/dyn/login.json?sid=$3")
  if [[ $result == *"sid"* ]]; then
    echo "$result"
    SESSION=$(echo "$result" | jq -r ".result.sid")
  elif [[ $result == *"err"* ]]; then
    echo "$result" | jq -r ".err"
    exit 1
  else
    exit 1
  fi
  echo "${SESSION}" >"$SESSION_PATH"

  return 0
}

# sid
logout_session() {
  echo "Logout existing session $SESSION"
  result=$(curl -s -k -X POST -H "Content-Type: application/json" -d "{}" "$PORTAL/dyn/logout.json?sid=$SESSION")
  echo "$result"
}

# zip, destination, sid
downloadZip() {
  SOURCE=$1
  DEST=$2

  echo "Download $SOURCE to $DEST.PART"

  if [[ -f "$DEST.PART" ]]; then
    rm "$DEST.PART"
  fi

  if curl -s -k -X POST -H "Content-Type: application/json" -d "{}" "$SOURCE?sid=$SESSION" --output "$DEST.PART"; then
    echo "Success: Move $DEST.PART" "$DEST"
    mv "$DEST.PART" "$DEST"
  fi
}

while getopts "p:r:g:x:la" options; do
  case "${options}" in
  p) PORTAL=${OPTARG} ;;
  r) REPORTS=${OPTARG} ;;
  g) GROUP=${OPTARG} ;;
  x) PASS=${OPTARG} ;;
  l) DOWNLOAD_LIVE=1 ;;
  a) DOWNLOAD_ARCHIVE=1 ;;
  :)
    echo "Error: -${OPTARG} requires an argument."
    exit_abnormal
    ;;
  *) exit_abnormal ;;
  esac
done

if [[ -z $REPORTS ]]; then
  echo "Reports -r is missing"
  exit_abnormal
fi

if [[ -f "$SESSION_PATH" ]]; then
  SESSION=$(cat $SESSION_PATH)
fi

print_env

if [[ -z $PORTAL ]]; then
  echo "Portal -p is missing"
  exit_abnormal
fi

if [[ -z $PASS ]]; then
  echo "Password -x is missing"
  exit_abnormal
fi

# clear temp directory
rm -rf "$TMP_DIR"

mkdir -p "$DATA_DIR"
mkdir -p "$TMP_DIR"

if [[ ! -z $SESSION ]]; then
  logout_session
fi

# login new user
if login_session "$GROUP" "$PASS" -eq 0; then
  echo "Successfully logged in"
else
  echo "User could not log in"
  exit 1
fi

# get reports
echo "Get reports $REPORTS"
SMA_FS_REPORT_PATH="/DIAGNOSE/$REPORTS/"

FILES=$(curl -s -k -X POST -H "Content-Type: application/json" -d "{\"destDev\": [], \"path\": \"$SMA_FS_REPORT_PATH\"}" "$PORTAL/dyn/getFS.json?sid=${SESSION}")
ARCHIVES=$(echo "$FILES" | jq -r ".result[.result | keys[0]][\"$SMA_FS_REPORT_PATH\"] | map_values(.f) | .[]" | grep ZIP | sort -h)
LIVE_FILES=$(echo "$FILES" | jq -r ".result[.result | keys[0]][\"$SMA_FS_REPORT_PATH\"] | map_values(.f) | .[]" | grep -v ZIP | sort -h)
FIRST_LIVE_FILE=$(echo "$LIVE_FILES" | cut -d" " -f1)
TODAY_FILE_NAME="${FIRST_LIVE_FILE%%.*}"
LIVE_DIR="${DATA_DIR%/}/${REPORTS}/$TODAY_FILE_NAME"

if [[ $DOWNLOAD_LIVE -eq 1 ]]; then
  if [[ -d $LIVE_DIR ]]; then
    rm -r "$LIVE_DIR"
  fi

  mkdir -p "$LIVE_DIR"

  if [[ -f "${LIVE_DIR}.ZIP" ]]; then
    rm "${LIVE_DIR}.ZIP"
  fi

  for file in $LIVE_FILES; do
    DESTINATION="$LIVE_DIR/$file"
    URL="$PORTAL/fs/DIAGNOSE/$REPORTS/$file"
    echo "Download $URL to $DESTINATION"
    curl -s -k -X POST -H "Content-Type: application/json" -d "{}" "$URL?sid=$SESSION" --output "$DESTINATION"
  done

  zip -jr "${LIVE_DIR}.ZIP" "$LIVE_DIR/"

  if [[ -d $LIVE_DIR ]]; then
    rm -r "$LIVE_DIR"
  fi
fi

if [[ $DOWNLOAD_ARCHIVE -eq 1 ]]; then
  for archive in $ARCHIVES; do
    DESTINATION="${DATA_DIR%/}/${REPORTS}/$archive"
    URL="$PORTAL/fs/DIAGNOSE/$REPORTS/$archive"

    if [[ ! -f "$DESTINATION" ]]; then
      downloadZip "$URL" "$DESTINATION"
      sleep 5
    fi
  done
fi

logout_session
