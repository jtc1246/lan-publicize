from curl_http import curl_http_get, curl_http_post
import socket
from myBasics import binToBase64, base64ToBin
from threading import Lock
from _thread import start_new_thread
import time
import json
from queue import Queue

IP = '127.0.0.1'
PORT = 11434
SERVER = 'http://jtc1246.com:7005'
PASSWORD = 'JTC'

CHECKS_PER_SECOND = 50
CHECH_UPDATE_TIMEOUT = 2
RETRT_TIMEOUT_FUNC = lambda x: min(1.0, 0.7 + x * 0.3)


class IdService:
    def __init__(self):
        self.lock = Lock()
        self.id = 0

    def get_id(self):
        with self.lock:
            self.id += 1
            return self.id - 1


connection_ids = set()
forward_waiting_blocks = {}  # block_id (int) -> bytes
forward_next_id = 0
forward_waiting_lock = Lock()  # only for forward_waiting_blocks and forward_next_id, don't lock forward_queues
forward_queues = {}  # id (int) -> queue
latest_block_id = -1
retrying_blocks = set()


def send_until_success(url: str, connection_id: int, block_id: int, data: bytes):
    times = 0
    headers = {
        'Connection-Id': str(connection_id),
        'Data-Id': str(block_id),
        'Password': PASSWORD
    }
    status = -1
    while (status not in (200, 429)):
        # temporarily data will also be accepted when 429
        timeout = RETRT_TIMEOUT_FUNC(times)
        _, status, _, _ = curl_http_post(url, headers, binToBase64(data), timeout)
        time.sleep(0.005)
        times += 1


def forward_write(socket: socket.socket, connection_id: int):
    while True:
        data = forward_queues[connection_id].get()
        if (data == False):
            break
        socket.send(data)


def read_backward(socket: socket.socket, connection_id: int):
    block_id = 0
    while True:
        data = socket.recv(65536)
        if (len(data) == 0):
            break
        start_new_thread(send_until_success, (SERVER + '/send_backward', connection_id, block_id, data))
        block_id += 1


def create_connection(connection_id: int):
    connection_ids.add(connection_id)
    forward_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    forward_socket.connect((IP, PORT))
    forward_queues[connection_id] = Queue()
    start_new_thread(forward_write, (forward_socket, connection_id))
    start_new_thread(read_backward, (forward_socket, connection_id))


def process_forward_waiting():
    global forward_next_id
    forward_waiting_lock.acquire()
    if (forward_next_id not in forward_waiting_blocks):
        forward_waiting_lock.release()
        return
    max_id = forward_next_id
    while True:
        if ((max_id + 1) in forward_waiting_blocks):
            max_id += 1
        else:
            break
    for id in range(forward_next_id, max_id + 1):
        msg = json.loads(forward_waiting_blocks[id])
        for connection_id, data in msg.items():
            connection_id = int(connection_id)
            if (connection_id not in connection_ids):
                create_connection(connection_id)
            forward_queues[connection_id].put(base64ToBin(data))
    forward_next_id = max_id + 1
    forward_waiting_lock.release()


def retry_one_block(block_id: int):
    url = SERVER + '/get_data'
    headers = {'Data-Id': str(block_id), 'Password': PASSWORD}
    status = -1
    times = 0
    while (status not in (200,)):
        # temporarily data will also be accepted when 429
        timeout = RETRT_TIMEOUT_FUNC(times)
        _, status, headers_, body = curl_http_get(url, headers, timeout)
        time.sleep(0.005)
        times += 1
    forward_waiting_lock.acquire()
    forward_waiting_blocks[block_id] = body
    forward_waiting_lock.release()
    process_forward_waiting()


def retry_prev_blocks():
    for i in range(forward_next_id, latest_block_id + 1):
        if (i in retrying_blocks or i in forward_waiting_blocks):
            continue
        start_new_thread(retry_one_block, (i,))


def check_forward_update():
    '''
    Only check once, should have a wrapper to continuously call this function
    '''
    global latest_block_id
    url = SERVER + '/get_update'
    headers = {'Success-Till': str(forward_next_id - 1), 'Password': PASSWORD}
    success, status, headers, body = curl_http_get(url, headers, timeout=CHECH_UPDATE_TIMEOUT)
    if (success == False):
        print(f'{int(time.time() * 1000)}: failed to get update, network error ot timeout')
        return
    if (status not in (200, 204)):
        print(f'{int(time.time() * 1000)} failed to get update, http status {status}')
        return
    if (status == 204):
        data_id = int(headers['Data-Id'])
        forward_waiting_lock.acquire()
        latest_block_id = max(latest_block_id, data_id)
        retry_prev_blocks()
        forward_waiting_lock.release()
        return
    data_id = int(headers['Data-Id'])
    print(f'{data_id}: {body}')
    forward_waiting_lock.acquire()
    assert (data_id >= forward_next_id)
    forward_waiting_blocks[data_id] = body
    latest_block_id = max(latest_block_id, data_id)
    retry_prev_blocks()
    forward_waiting_lock.release()
    process_forward_waiting()


def check_update_forever():
    while True:
        start_new_thread(check_forward_update, ())
        time.sleep(1 / CHECKS_PER_SECOND)


start_new_thread(check_update_forever, ())
while True:
    time.sleep(10)
