from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import socket
from threading import Lock
from _thread import start_new_thread
from queue import Queue
from time import sleep
from myBasics import binToBase64, base64ToBin  # pip install myBasics
import json


PASSWORD = 'JTC'
PUBLIC_PORT = 11434
INNER_PORT = 7005


class IdService:
    def __init__(self):
        self.lock = Lock()
        self.id = 0

    def get_id(self):
        with self.lock:
            self.id += 1
            return self.id - 1
    
    def current(self):
        with self.lock:
            return self.id - 1


connection_id_service = IdService()
http_id_service = IdService()
forward_queues = {}  # id (int) -> queue
backward_queues = {}  # id (int) -> queue
forward_buffer_size = {}  # id (int) -> size (int)
backward_buffer_size = {}  # id (int) -> size (int)
prepare_data_lock = Lock()
forward_data_caches = {}  # data_id (int) -> data (bytes)
forward_data_caches_lock = Lock()
backward_next_id = {}  # connection_id (int) -> next_id (int)
backward_waiting_blocks = {}  # connection_id (int) -> dict {data_id (int) -> data (bytes)}
backward_waiting_locks = {}  # connection_id (int) -> Lock


def forward(client_socket, connection_id):
    while True:
        while (forward_buffer_size[connection_id] >= 10 * 1024 * 1024):
            sleep(0.005)
        data = client_socket.recv(1024)
        # print(data)
        if (len(data) == 0):
            forward_queues[connection_id].put(False)
            break
        forward_buffer_size[connection_id] += len(data)
        forward_queues[connection_id].put(data)


def backward(client_socket, connection_id):
    while True:
        data = backward_queues[connection_id].get()
        if (data == False):
            del backward_queues[connection_id]
            del backward_buffer_size[connection_id]
            del backward_next_id[connection_id]
            del backward_waiting_blocks[connection_id]
            del backward_waiting_locks[connection_id]
            break
        backward_buffer_size[connection_id] -= len(data)
        client_socket.send(data)


def handle_connection(client_socket):
    connection_id = connection_id_service.get_id()
    forward_queues[connection_id] = Queue()
    backward_queues[connection_id] = Queue()
    forward_buffer_size[connection_id] = 0
    backward_buffer_size[connection_id] = 0
    backward_next_id[connection_id] = 0
    backward_waiting_blocks[connection_id] = {}
    backward_waiting_locks[connection_id] = Lock()
    start_new_thread(forward, (client_socket, connection_id))
    start_new_thread(backward, (client_socket, connection_id))


def start_tcp_server():
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(('0.0.0.0', PUBLIC_PORT))
    server.listen(300)
    print(f"[*] Listening on 0.0.0.0:{PUBLIC_PORT}")

    while True:
        client_socket, addr = server.accept()
        print(f"[*] Accepted connection from {addr[0]}:{addr[1]}")
        start_new_thread(handle_connection, (client_socket,))


def prepare_data():
    prepare_data_lock.acquire()
    datas = {}
    total_size = 0
    while (True):
        new_data = False
        full = False
        for id in list(forward_queues.keys()):
            queue = forward_queues[id]
            if (queue.empty()):
                continue
            data = queue.get()
            if (data == False):
                del forward_buffer_size[id]
                continue
            new_data = True
            if (id not in datas):
                datas[id] = []
            datas[id].append(data)
            forward_buffer_size[id] -= len(data)
            total_size += len(data)
            if (total_size >= 100 * 1024):
                full = True
                break
        if (full):
            break
        if (not new_data):
            break
    if (len(datas) == 0):
        prepare_data_lock.release()
        return False
    data_id = http_id_service.get_id()
    prepare_data_lock.release()
    new_datas = {}
    for id, data_list in datas.items():
        new_datas[id] = binToBase64(b''.join(data_list))
    return (data_id, json.dumps(new_datas, ensure_ascii=False).encode('utf-8'))


def process_backward_waiting(connection_id):
    backward_waiting_locks[connection_id].acquire()
    if (backward_next_id[connection_id] not in backward_waiting_blocks[connection_id]):
        backward_waiting_locks[connection_id].release()
        return
    next_id = backward_next_id[connection_id]
    max_id = next_id
    while True:
        if ((max_id + 1) in backward_waiting_blocks[connection_id]):
            max_id += 1
        else:
            break
    for block_id in range(next_id, max_id + 1):
        data = backward_waiting_blocks[connection_id][block_id]
        del backward_waiting_blocks[connection_id][block_id]
        backward_queues[connection_id].put(data)
        backward_buffer_size[connection_id] += len(data)
    backward_next_id[connection_id] = max_id + 1
    backward_waiting_locks[connection_id].release()


def delete_success_till(success_till: int):
    if (success_till == -1):
        return
    with forward_data_caches_lock:
        for id in list(forward_data_caches.keys()):
            if (id <= success_till):
                del forward_data_caches[id]


class Request(BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'
    
    def send_response(self, code):
        return self.send_response_only(code)
    
    def do_GET(self):
        path = self.path
        if (path.startswith('/get_update') == False and path.startswith('/get_data') == False):
            self.send_response(404)
            self.send_header('Content-Length', 0)
            self.send_header('Connection', 'keep-alive')
            self.send_cache_headers()
            self.end_headers()
            self.wfile.flush()
            return
        if ('Password' not in self.headers or self.headers['Password'].upper() != PASSWORD):
            self.send_response(400)
            self.send_header('Content-Length', 0)
            self.send_header('Connection', 'keep-alive')
            self.send_cache_headers()
            self.end_headers()
            self.wfile.flush()
            return
        if (path.startswith('/get_data')):
            data_id = int(self.headers['Data-Id'])
            if (data_id in forward_data_caches):
                data = forward_data_caches[data_id]
                self.send_response(200)
                self.send_header('Content-Length', len(data))
                self.send_header('Connection', 'keep-alive')
                self.send_cache_headers()
                self.end_headers()
                self.wfile.write(data)
                self.wfile.flush()
                return
            self.send_response(404)
            self.send_header('Content-Length', 0)
            self.send_header('Connection', 'keep-alive')
            self.send_cache_headers()
            self.end_headers()
            self.wfile.flush()
            return
        result = prepare_data()
        if (result == False):
            self.send_response(204)
            data_id = http_id_service.current()
            self.send_header('Content-Length', 0)
            self.send_header('Connection', 'keep-alive')
            self.send_header('Data-Id', data_id)
            self.send_cache_headers()
            self.end_headers()
            self.wfile.flush()
            success_till = int(self.headers['Success-Till'])
            delete_success_till(success_till)
            return
        data_id, data = result
        forward_data_caches[data_id] = data
        self.send_response(200)
        self.send_header('Content-Length', len(data))
        self.send_header('Connection', 'keep-alive')
        self.send_header('Data-Id', data_id)
        self.send_cache_headers()
        self.end_headers()
        self.wfile.write(data)
        self.wfile.flush()
        with forward_data_caches_lock:
            forward_data_caches[data_id] = data
        success_till = int(self.headers['Success-Till'])
        delete_success_till(success_till)

    def do_POST(self):
        path = self.path
        if (path.startswith('/send_backward') == False):
            self.send_response(404)
            self.send_header('Content-Length', 0)
            self.send_header('Connection', 'keep-alive')
            self.send_cache_headers()
            self.end_headers()
            self.wfile.flush()
            return
        if ('Password' not in self.headers or self.headers['Password'].upper() != PASSWORD):
            self.send_response(400)
            self.send_header('Content-Length', 0)
            self.send_header('Connection', 'keep-alive')
            self.send_cache_headers()
            self.end_headers()
            self.wfile.flush()
            return
        data = self.rfile.read(int(self.headers['Content-Length']))
        connection_id = int(self.headers['Connection-Id'])
        data_id = int(self.headers['Data-Id'])
        data = base64ToBin(data.decode('utf-8'))
        if (backward_buffer_size[connection_id] >= 10 * 1024 * 1024):
            self.send_response(429)  # but data still accepted
        else:
            self.send_response(200)
        self.send_header('Content-Length', 0)
        self.send_header('Connection', 'keep-alive')
        self.send_header('Buffer-Size', backward_buffer_size[connection_id])
        self.send_cache_headers()
        self.end_headers()
        self.wfile.flush()
        backward_waiting_locks[connection_id].acquire()
        backward_waiting_blocks[connection_id][data_id] = data
        backward_waiting_locks[connection_id].release()
        process_backward_waiting(connection_id)
        
    def send_cache_headers(self):
        self.send_header('Cache-Control', 'no-store, no-cache, must-revalidate, max-age=0, private')
        self.send_header('Pragma', 'no-cache')
        self.send_header('Expires', 'Thu, 01 Jan 1970 00:00:00 GMT')
        


server = ThreadingHTTPServer(('0.0.0.0', INNER_PORT), Request)
start_new_thread(server.serve_forever, ())
start_new_thread(start_tcp_server, ())

while True:
    sleep(10)
