import subprocess
import json
from typing import Tuple
from subprocess import DEVNULL
import traceback
from secrets import token_hex


def is_ascii(s: str) -> bool:
    return len(s.encode('utf-8')) == 1


def escape_one(s: str) -> str:
    if (is_ascii(s) == False):
        return s
    if (s in '\\$"`'):
        return '\\' + s
    return s


def safe_sh_escape(s: str) -> str:
    # IEEE Std 1003.1-2017: https://pubs.opengroup.org/onlinepubs/9699919799/utilities/V3_chap02.html
    return ' "' + ''.join([escape_one(c) for c in s]) + '" '  # add space does nothing bad, but what if forgot in outside?


def curl_http_get(url: str, headers: dict = {}, timeout: float = 0.5) -> Tuple[bool, int, dict, str]:
    '''
    Send a HTTP GET request using curl, don't rely on python http library

    Returns: (success, status, headers, body), body is str
    
    Response data can only be str, not bytes
    '''
    url += '/' + token_hex(64)
    command = f'curl -X GET '
    headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, private, max-age=0'
    headers['Pragma'] = 'no-cache'
    headers['Expires'] = 'Thu, 01 Jan 1970 00:00:00 GMT'
    for k, v in headers.items():
        command += '-H '
        command += safe_sh_escape(f'{k}: {v}') + ' '  # don't rely on the property of adding space
    if ('User-Agent' not in headers):
        command += '-H User-Agent: '
    if ('Accept' not in headers):
        command += '-H Accept: '
    if ('Accept-Encoding' not in headers):
        command += '-H Accept-Encoding: '
    command += '--max-time ' + str(timeout) + ' '
    command += '--no-compressed '
    command += '-D - '
    command += safe_sh_escape(url)
    try:
        resp = subprocess.check_output(command, shell=True, stderr=DEVNULL)
    except:
        return (False, -1, {}, '')
    try:
        resp = resp.decode('utf-8')
        first_line = resp[:resp.find('\r\n')]
        first_line = first_line.split(' ')
        status = int(first_line[1])
        headers_part = resp[resp.find('\r\n') + 2: resp.find('\r\n\r\n')]
        headers = {}
        for line in headers_part.split('\r\n'):
            headers[line[:line.find(':')]] = line[line.find(':') + 2:]
        body = resp[resp.find('\r\n\r\n') + 4:]
        headers_lower = {}
        for k, v in headers.items():
            headers_lower[k.lower()] = v
        if ('content-length' in headers_lower):
            if (len(body.encode('utf-8')) != int(headers_lower['content-length'])):
                assert (False)
        return (True, status, headers, body)
    except:
        traceback.print_exc()
        return (False, -1, {}, '')


def curl_http_post(url: str, headers: dict = {}, body: str = '', timeout: float = 0.5) -> Tuple[bool, int, dict, str]:
    '''
    Send a HTTP POST request using curl, don't rely on python http library

    body can only be str, not bytes

    Returns: (success, status, headers, body), body is str
    
    Response data can only be str, not bytes
    '''
    url += '/' + token_hex(64)
    command = f'curl -X POST '
    headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, private, max-age=0'
    headers['Pragma'] = 'no-cache'
    headers['Expires'] = 'Thu, 01 Jan 1970 00:00:00 GMT'
    for k, v in headers.items():
        command += '-H '
        command += safe_sh_escape(f'{k}: {v}') + ' '  # don't rely on the property of adding space
    if ('User-Agent' not in headers):
        command += '-H User-Agent: '
    if ('Accept' not in headers):
        command += '-H Accept: '
    if ('Accept-Encoding' not in headers):
        command += '-H Accept-Encoding: '
    if ('Content-Type' not in headers):
        command += '-H Content-Type: '
    command += '-H Expect: '
    if ('Content-Length' not in headers):
        command += '-H "Content-Length: ' + str(len(body.encode('utf-8'))) + '" '
    command += '--max-time ' + str(timeout) + ' '
    command += '--no-compressed '
    command += '-D - '
    command += safe_sh_escape(url)
    command += ' -d ' + safe_sh_escape(body)
    try:
        resp = subprocess.check_output(command, shell=True, stderr=DEVNULL)
    except:
        return (False, -1, {}, '')
    try:
        resp = resp.decode('utf-8')
        first_line = resp[:resp.find('\r\n')]
        first_line = first_line.split(' ')
        status = int(first_line[1])
        headers_part = resp[resp.find('\r\n') + 2: resp.find('\r\n\r\n')]
        headers = {}
        for line in headers_part.split('\r\n'):
            headers[line[:line.find(':')]] = line[line.find(':') + 2:]
        body = resp[resp.find('\r\n\r\n') + 4:]
        headers_lower = {}
        for k, v in headers.items():
            headers_lower[k.lower()] = v
        if ('content-length' in headers_lower):
            if (len(body.encode('utf-8')) != int(headers_lower['content-length'])):
                assert (False)
        return (True, status, headers, body)
    except:
        traceback.print_exc()
        return (False, -1, {}, '')


if __name__ == '__main__':
    # s = ''
    # for i in range(1, 128):
    #     # \0 can't be in the sh arguments
    #     s += chr(i)
    # tests = [s, '$(abcd)', '${abcd}', '$(', '$(abcd', '$()', '${}', '${', '', '${abcd']
    # tests += ['``', '`abcd`', '`', '`abc', '`ab"', "`ab'", '`ab"`', "`ab'`", '`ab"cd`', "`ab'cd`"]
    # for s in tests:
    #     escaped = safe_sh_escape(s)
    #     '''
    #     import sys
    #     import json
    
    #     arg = sys.argv[1]
    #     print(json.dumps([arg]))
    #     '''
    #     result = subprocess.check_output('python3 test.py ' + escaped, shell=True)
    #     result = result.decode('utf-8')[:-1]
    #     print(result)
    #     assert (result == json.dumps([s]))
    print(curl_http_get('https://google.com/'))
