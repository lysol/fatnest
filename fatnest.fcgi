#!/usr/bin/python
from flup.server.fcgi import WSGIServer
from fatnest import app

if __name__ == '__main__':
    WSGIServer(app, bindAddress=('127.0.0.1', 8000)).run()
