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

from sma import login, logout, download_file, download_files_in_path, chunks_of, download_file_in_memory

# thanks to https://chase-seibert.github.io/blog/2014/03/21/python-multilevel-argparse.html
class SMA(object):

    def __init__(self):
        parser = argparse.ArgumentParser(
            description='Pretends to be git',
            usage='''sma <command> [<args>]

The most commonly used sma commands are:
   download     Record changes to the repository
   save         Download objects and refs from another repository
''')
        parser.add_argument('command', help='Subcommand to run')
        # parse_args defaults to [1:] for args, but you need to
        # exclude the rest of the args too, or validation will fail
        args = parser.parse_args(sys.argv[1:2])
        function_name = 'command_{}'.format(args.command)
        if not hasattr(self, function_name):
            print('Unrecognized command')
            parser.print_help()
            exit(1)
        # use dispatch pattern to invoke method with same name
        getattr(self, function_name)(sys.argv[2:])

    # #####################################################################
    def command_logout(self, arguments):
        parser = argparse.ArgumentParser(description='Record changes to the repository')
        # prefixing the argument with -- means it's optional
        parser.add_argument('--portal')
        parser.add_argument('--sid')

        args = parser.parse_args(arguments)
        args.portal = self._fix_url(args.portal)

        print(args)

        logout(args.portal, args.sid)

    # #####################################################################
    def command_download(self, arguments):
        parser = argparse.ArgumentParser(description='Record changes to the repository')
        # prefixing the argument with -- means it's optional
        parser.add_argument('portal')
        parser.add_argument('group')
        parser.add_argument('password')
        parser.add_argument('reports')

        # now that we're inside a subcommand, ignore the first
        # TWO argvs, ie the command (git) and the subcommand (commit)
        args = parser.parse_args(arguments)

        args.portal = self._fix_url(args.portal)

        sid = login(args.portal, args.group, args.password)
        if sid:
            download_files_in_path(args.portal, sid, args.reports)
            logout(args.portal, sid)

    # #####################################################################
    def command_save(self, arguments):
        parser = argparse.ArgumentParser(description='Download objects and refs from another repository')

        parser.add_argument('command', help='today')
        args = parser.parse_args(arguments[0:1])
        function_name = 'command_save_{}'.format(args.command)
        if not hasattr(self, function_name):
            print('Unrecognized sub command {}'.format(args.command))
            exit(1)
        # use dispatch pattern to invoke method with same name
        getattr(self, function_name)(arguments[1:])

        # parser.add_argument('--portal', required=True)
        # parser.add_argument('--group', required=True)
        # parser.add_argument('--password', required=True)
        # parser.add_argument('--reports', required=True)
        # parser.add_argument('--influx', required=True)

        # data_path = 'data/' + args.reports
        # zips = [join(data_path, f) for f in listdir(data_path) if isfile(join(data_path, f))]
        # for zip in zips:
        #     # open archive containing many csv files for the day
        #     with ZipFile(zip) as archive:
        #         fileNames = archive.namelist()

        #         # loop through every file and read its content
        #         for fileName in fileNames:
        #             with TextIOWrapper(archive.open(fileName), encoding="utf-8") as file:
        #                 lines = [line for line in file.readlines()]

        #                 self._send_lines(lines)


    # #####################################################################
    def command_save_today(self, arguments):
        parser = argparse.ArgumentParser(description='Download objects and refs from another repository')

        parser.add_argument('--portal', required=True)
        parser.add_argument('--group', choices=['istl', 'user'], default='istl')
        parser.add_argument('--password', required=True)
        parser.add_argument('--reports', choices=['ONLINE', 'ONLINE5M'], default='ONLINE5M')
        parser.add_argument('--influx', required=True)

        args = parser.parse_args(arguments)
        print(args)

        portal = self._fix_url(args.portal)

        sid = login(portal, args.group, args.password)
        if sid:
            urls = download_files_in_path(portal, sid, args.reports, '((DA\d{6})\.(\d+|CSV))')
            for url in urls:
                url = url + '?sid=' + sid
                content = download_file_in_memory(url)
            logout(portal, sid)

    def _send_lines(self, lines, influx):
        if len(lines) <= 8: return

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
                    return

                print('Send chunk with {} elements'.format(len(chunk)))
                x = '{}'.format('\n'.join(chunk)).encode()
                host = self._fix_url(influx + ':8086')
                response = requests.post(host + 'write?db=vault&precision=s', x)
                if response.status_code != 204:
                    print(response)

    def _fix_url(self, url):
        if not url.startswith('https://') and not url.startswith('http://'):
            url = 'http://' + url

        if not url.endswith('/'):
            url = url + '/'

        return url

def main():
    urllib3.disable_warnings()
    SMA()

if __name__ == "__main__":
    main()
