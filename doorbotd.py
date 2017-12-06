#!/usr/bin/env python

import logging
import socket
import sys
import sqlite3
import os

import doorbot
import doorio
import recoverserial


def path_relative(name):
    return os.path.join(os.path.dirname(__file__), name)


auth_dev = {
    'dev': "/dev/ttyAUTH",
    'baudrate': 9600,
}

lock_dev = {
    'dev': "/dev/ttyLOCK",
    'baudrate': 9600,
}

dbfile = path_relative("db/user.db")
logfile = path_relative("doorbot.log")

bindhost, port = '::1', 4242

sock = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
sock.bind((bindhost, port))
sock.listen(5)

logging.basicConfig(filename=logfile, format="%(asctime)-15s: %(message)s", level=logging.INFO)
log = logging.getLogger("doorbotd")

log.info("Doorbot started")

conn = sqlite3.connect(dbfile)

auth = recoverserial.RecoverSerial(auth_dev['dev'], auth_dev['baudrate'])
lock = recoverserial.RecoverSerial(lock_dev['dev'], lock_dev['baudrate'])

door_io = doorio.DoorIO(auth_serial=auth, lock_serial=lock, socket=sock)
doorbot = doorbot.Doorbot(conn, door_io)


sys.exit(0 if doorbot.run() else 1)
