#!/usr/bin/env python3

from os import listdir
from os.path import isfile, join
from urllib.parse import urljoin
import urllib3
import os
from zipfile import ZipFile
import csv
from io import TextIOWrapper
import requests
import datetime
import time
from sma_parser import create_column_type_definition
from sma_parser import create_column_type_definition

urllib3.disable_warnings()

def login(portal, group, password):
    print('LOGIN')
    payload = {'right': group, 'pass': password}
    url = urljoin(portal, '/dyn/login.json')
    headers = {
        'Content-Type': 'application/json;charset=utf-8'
    }
    cookies = {
        'deviceClass443':          '1',
        'tmhDynamicLocale.locale': 'en-us'
    }

    request = requests.post(url, json=payload, verify=False, headers=headers, cookies=cookies)
    response = request.json()
    print(response)
    if 'err' in response:
        return False
    elif 'result' in response:
        return response['result']['sid']


def logout(portal, sid):
    print('LOGOUT')
    payload = {}
    url = urljoin(portal, '/dyn/logout.json')
    params = {
        'sid': sid
    }

    request = requests.post(url, params=params, json=payload, verify=False)
    response = request.json()
    print(response)


def download_file(url, downloadDirectory, fileName):
    cwd = os.getcwd()
    path = os.path.join(cwd, 'data', downloadDirectory)
    if not os.path.isdir(path):
        try:
            os.makedirs(path)
        except OSError:
            print("Creation of the directory %s failed" % path)
            return False

    path = os.path.join(path, fileName)
    print(f'Download {url} to {path}')

    r = requests.get(url, verify=False)

    with open(path, 'wb') as f:
        f.write(r.content)


def get_fs(portal, sid, path):
    print('GET FS')
    payload = {
        'path':    '/DIAGNOSE/' + path + '/',
        'destDev': []
    }
    headers = {
        'Content-Type': 'application/json;charset=utf-8'
    }
    url = urljoin(portal, '/dyn/getFS.json')
    params = {
        'sid': sid
    }

    request = requests.post(url, params=params, json=payload, verify=False, headers=headers)
    response = request.json()

    if 'err' in response:
        return False
    elif 'result' in response:
        for deviceId, directory in response['result'].items():
            for directoryName, fileList in directory.items():
                for file in fileList:
                    if 'f' in file:
                        fileName = file['f']
                        if '.ZIP' in fileName:
                            # https://sma3006162062.local/fs/DIAGNOSE/ONLINE5M/DA200603.ZIP?sid=FXANtoJ7QMQ7YopA
                            url = f'{portal}fs{directoryName}{fileName}'
                            url = url + '?sid=' + sid

                            download_file(url, path, fileName)


PORTAL = 'https://sma3006162062.local/'
sid = login(PORTAL, 'istl', '1')
if sid:
    get_fs(PORTAL, sid, 'ONLINE5M')
    get_fs(PORTAL, sid, 'ONLINE')
    logout(PORTAL, sid)

def chunks_of(l, n):
    # For item i in a range that is a length of l,
    for i in range(0, len(l), n):
        # Create an index range for l of n items:
        yield l[i:i+n]

data_path = 'data/ONLINE5M'
zips = [join(data_path, f) for f in listdir(data_path) if isfile(join(data_path, f))]
for zip in zips:
    # open archive containing many csv files for the day
    with ZipFile(zip) as archive:
        fileNames = archive.namelist()

        # loop through every file and read its content
        for fileName in fileNames:
            with TextIOWrapper(archive.open(fileName), encoding="utf-8") as file:
                lines = [line for line in file.readlines()]

                if len(lines) <= 8: continue

                # parse columns and prepent the DateTime column because its always empty in the export
                columns = ['DateTime'] + [column.replace('.', '_').lower() for column in lines[5].replace('\n','').split(',') if column]

                # skip the lines containing the headers
                values = lines[8:]

                # split every line by ,. some files contain an extra new line at the end so we need to remove it
                entries = [entry.replace('\n','').split(',') for entry in values]

                if len(entries):
                    print('Log {} entries from {}'.format(len(entries), fileName))
                    request_data = []
                    for entry in entries:
                        actual_values = {column: entry[index] for index, column in enumerate(columns) if entry[index]}

                        if len(actual_values) > 1:
                            date = datetime.datetime.strptime(actual_values['DateTime'], "%d.%m.%Y %H:%M:%S")
                            timetuple = date.timetuple()
                            timestamp = int(time.mktime(timetuple))

                            data = ['{},source=pv value={} {}'.format(key, value, timestamp) 
                                    for index, (key, value) in enumerate(actual_values.items())
                                    if key != 'DateTime']
                            
                            request_data = request_data + data

                    chunks = chunks_of(request_data, 25000)
                    
                    for chunk in chunks:
                        if len(chunk) == 0:
                            continue

                        print('Send chunk with {} elements'.format(len(chunk)))
                        x = '{}'.format('\n'.join(chunk)).encode()
                        response = requests.post('http://192.168.2.2:8086/write?db=vault&precision=s', x)
                        if response.status_code != 204:
                            print(response)

# curl -i  -XPOST "http://192.168.2.2:8086/write?db=vault" --data-binary 'gridms_hz_max,source=pv value=50.100 1602338100'
