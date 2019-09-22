#!/bin/bash

# How to use
# PORTAL="https://YOUR_SMA_ADDRESS" REPORTS="/DIAGNOSE/ONLINE5M/" GROUP=istl PASS=1111 ./download_files.sh

if [ -z $PORTAL ]; then
  echo "PORTAL variable is missing"
  echo "Example:"
  echo "PORTAL=\"https://sma1234567890\""
  exit 1
fi

if [ -z $REPORTS ]; then
  echo "REPORTS variable is missing"
  echo "Example:"
  echo "REPORTS=\"/DIAGNOSE/ONLINE5M/\""
  exit 1
fi

if [ -z $GROUP ]; then
  echo "GROUP variable is missing"
  echo "Example:"
  echo "GROUP=istl"
  exit 1
fi

if [ -z $PASS ]; then
  echo "PASS variable is missing"
  echo "Example:"
  echo "PASS=1111"
  exit 1
fi

DATA_DIR="data$REPORTS"
mkdir -p "$DATA_DIR"

# sid
logout() {
  result=$(curl -s -k -X POST -H "Content-Type: application/json" -d "{}" "$PORTAL/dyn/logout.json?sid=$1")
  echo $result
}

# zip, sid
downloadZip() {
  ZIP=$1
  SID=$2
  DEST=data$REPORTS$ZIP
  SOURCE=$PORTAL/fs$REPORTS$ZIP
  if [ ! -f "$DEST" ]; then
    echo "Download $SOURCE to $DEST"
    curl -s -k -X POST -H "Content-Type: application/json" -d "{}" "$SOURCE?sid=$SID" --output "$DEST"
  fi
}

# clear temp directory
rm -rf temp/*

# logout latest session in case something went wrong
echo "Load existing session"
session=$(cat session.txt)
echo $session

echo "Logout"
logout "$session"
echo $session

# login new user
echo "Login $1 $2"
result=$(curl -s -k -X POST -H "Content-Type: application/json" -d "{\"right\": \"$GROUP\", \"pass\": \"$PASS\"}" "$PORTAL/dyn/login.json?sid=$3")
if [[ $result == *"sid"* ]]; then
  echo $result
  session=$(echo $result | jq -r ".result.sid")
elif [[ $result == *"err"* ]]; then
  echo $result | jq -r ".err"
  exit 1
else
  exit 1
fi
echo $session >session.txt

# get reports
echo "Get reports $REPORTS"
files=$(curl -s -k -X POST -H "Content-Type: application/json" -d "{\"destDev\": [], \"path\": \"$REPORTS\"}" "$PORTAL/dyn/getFS.json?sid=$session")
files=$(echo $files | jq -r ".result[.result | keys[0]][\"$REPORTS\"] | map_values(.f) | .[]" | grep ZIP | sort -h)
echo "$files"
for file in $files; do
  downloadZip "$file" "$session"
done

# get current day
echo "Get current day from $REPORTS"
files=$(curl -s -k -X POST -H "Content-Type: application/json" -d "{\"destDev\": [], \"path\": \"$REPORTS\"}" "$PORTAL/dyn/getFS.json?sid=$session")
files=$(echo $files | jq -r ".result[.result | keys[0]][\"$REPORTS\"] | map_values(.f) | .[]" | grep -v ZIP | sort -h)
echo "$files"
first_file=$(echo $files | cut -d ' ' -f1)
name="${first_file%.*}"
echo "Create dir ${DATA_DIR}today"
mkdir -p ${DATA_DIR}today
for file in $files; do
  DEST=${DATA_DIR}today/$file
  SOURCE=$PORTAL/fs$REPORTS$file
  echo "Download $SOURCE to $DEST"
  curl -s -k -X POST -H "Content-Type: application/json" -d "{}" "$SOURCE?sid=$session" --output "$DEST"
done

# create zip for the current day
echo "Create zip from data of the current day"
zip -j ${DATA_DIR}today.ZIP ${DATA_DIR}today/*

# logout current session
echo "Logout"
logout "$session"
rm -f session.txt
