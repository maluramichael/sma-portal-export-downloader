# sma-portal-export-downloader

<!-- links:start -->
[![Support me on Ko-fi](https://malura.de/assets/badge/kofi.svg)](https://malura.de/go/kofi?ref=sma-portal-export-downloader)
[![Check out my page](https://malura.de/assets/badge/malura.svg)](https://malura.de/go/site?ref=sma-portal-export-downloader)
<!-- links:end -->

Download the diagnostic exports of an SMA inverter (`ONLINE` and `ONLINE5M`, one ZIP per day) and
import them into InfluxDB. Tested with a Sunny Tripower 6.0.

Two scripts, plain Python 3 with `requests`:

- `download_sma.py` logs in to the inverter, lists its exports and downloads the ones you do not have yet.
  Every ZIP is validated, a broken download never ends up in the target folder.
- `import_sma_to_influx.py` reads the downloaded `ONLINE5M` ZIPs and writes the values to InfluxDB (line protocol, in batches).

## Setup

```sh
pip install -r requirements.txt
```

## Download

The inverter address and the password are read from the environment, so the password does not show up in `ps`.

```sh
export SMA_HOST=192.168.1.50        # or pass --host
export SMA_PASS=...                 # password of the user group
python3 download_sma.py --dest /data/pv          # ONLINE5M ZIPs go to /data/pv/ONLINE5M/
python3 download_sma.py -r ONLINE --dest /data/pv
```

| Option | Environment | Meaning |
| --- | --- | --- |
| `--host` | `SMA_HOST` | Inverter address, `https://` is added if missing |
| (none) | `SMA_PASS` | Password, required |
| `--group` | `SMA_GROUP` | `istl` (installer, default) or `user` |
| `--dest` | `SMA_DATA_DIR` | Download directory, default `./data`. Files go to `<dest>/<report>/` |
| `-r` | | `ONLINE5M` (default) or `ONLINE` |
| `--one NAME.ZIP` | | Download one file |
| `--redownload-broken` | | Find invalid ZIPs in the target folder and download them again |
| `--dry-run` | | List what would be downloaded |
| | `SMA_SESSION_FILE` | Where the session id is kept, default `<tmp>/sma_session.txt` |

The inverter uses a self-signed certificate, so certificate checks are off.

## Import into InfluxDB

```sh
export SMA_DATA_DIR=/data/pv                  # same folder as above
export INFLUX_URL=http://localhost:8086/write
export INFLUX_DB=sma
export INFLUX_USER=...  INFLUX_PASS=...       # optional
python3 import_sma_to_influx.py --dry-run     # preview
python3 import_sma_to_influx.py --from 2026-01-01
```

`--data-dir` overrides the folder. The column selection lives in `COLUMN_MAP` at the top of the script. Timestamps are
converted with the local time zone of the machine the script runs on.

## Cron

```
0 4 * * 0  SMA_HOST=192.168.1.50 SMA_PASS=... SMA_DATA_DIR=/data/pv python3 /path/download_sma.py && python3 /path/import_sma_to_influx.py
```

## Tests

```sh
python3 -m unittest test_sma
```

The inverter and InfluxDB are mocked.
