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
import argparse
import sys
import re
import io
from contextlib import closing

def login(portal, group, password):
    print('Login', portal, group, password)
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
    print('# LOGOUT')
    payload = {}
    url = urljoin(portal, '/dyn/logout.json?sid=' + sid)

    print(url)

    response = requests.post(url, json=payload, verify=False)

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
    if not os.path.isfile(path):
        print(f'Download {url} to {path}')

        r = requests.get(url, verify=False)

        with open(path, 'wb') as f:
            f.write(r.content)

def download_file_in_memory(url):
    r = requests.get(url, verify=False)
    data = r.content
    print(data)
    bytes = io.BytesIO(data)
    return data

def download_files_in_path(portal, sid, report_type, file_filter):
    matcher = re.compile(file_filter)
    print('GET FS')
    payload = {
        'path':    '/DIAGNOSE/' + report_type + '/',
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

    files = []

    if 'err' in response:
        return False
    elif 'result' in response:
        for deviceId, directory in response['result'].items():
            for directoryName, fileList in directory.items():
                for file in fileList:
                    if 'f' in file:
                        fileName = file['f']
                        if matcher.search(fileName):
                            # https://sma3006162062.local/fs/DIAGNOSE/ONLINE5M/DA200603.ZIP?sid=FXANtoJ7QMQ7YopA
                            url = f'{portal}fs{directoryName}{fileName}'
                            files.append(url)
                            #url = url + '?sid=' + sid
                            #download_file(url, report_type, fileName)
    return files

def chunks_of(l, n):
    # For item i in a range that is a length of l,
    for i in range(0, len(l), n):
        # Create an index range for l of n items:
        yield l[i:i+n]
