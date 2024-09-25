# lan-publicize

## Introduction

Make your LAN device's port WAN accessible. This requires a WAN server.

## Usage

### Server

Set `PASSWORD`, `PUBLIC_PORT`, `INNER_PORT` in `server.py`, and then run `server.py`.

Note: `PUBLIC_PORT` is the port other people visit, `INNER_PORT` is used for LAN device to communicate with the server.

### LAN device

Set the `PASSWORD`, `SERVER`, `IP` and `PORT` in `publicize.py`, and then run `publicize.py`.

Note: `PASSWORD` should be the same as the server, `SERVER` is a http(s) url, that can be visited by this device, `IP` and `PORT` are the ip and port that will forward to.

## How it works

The server will establish TCP connections with the user. The LAN device communicates with the server through HTTP requests. It will receive the TCP data and send to the target IP and port, backword is also the same. The HTTP is realized through curl, not python HTTP library.

## Why design like this

In my school's server, it only allows HTTP/HTTPS traffic, any other types, like SSH, will be blocked. Also, it only allows to use HTTP through curl or wget, we can't use in python or C++. So I use HTTP to communicate and use curl for HTTP. I know this really slow.
