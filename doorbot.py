#!/usr/bin/env python

import logging
import time

import userdb

log = logging.getLogger("doorbot")

AWAIT_RFID, AWAIT_PIN, OPEN, RELOCK, ADD_KEY, ADD_KEY_PIN_NEW, ADD_KEY_PIN_VERIFY, RESET_PIN, PINCHANGE_OLD,\
    PINCHANGE_NEW, PINCHANGE_VERIFY, OPEN_MODE = range(12)

statenames = {
    AWAIT_RFID: 'AWAIT_RFID',
    AWAIT_PIN: 'AWAIT_PIN',
    OPEN: 'OPEN',
    RELOCK: 'RELOCK',
    ADD_KEY: 'ADD_KEY',
    ADD_KEY_PIN_NEW: 'ADD_KEY_PIN_NEW',
    ADD_KEY_PIN_VERIFY: 'ADD_KEY_PIN_VERIFY',
    RESET_PIN: 'RESET_PIN',
    PINCHANGE_OLD: 'PINCHANGE_OLD',
    PINCHANGE_NEW: 'PINCHANGE_NEW',
    PINCHANGE_VERIFY: 'PINCHANGE_VERIFY',
    OPEN_MODE: 'OPEN_MODE',
}

PIN_TIMEOUT = 15
UNLOCK_TIMEOUT = 5
RELOCK_TIMEOUT = 1


class Doorbot(object):
    def __init__(self, dbconn, door_io):
        self._dbconn = dbconn
        self._door_io = door_io
        self._timeout = None
        self._state = None
        self._rfid = ''
        self._pin = ''
        self._orig_pin = ''

    # states

    def set_state(self, state):
        log.debug("state = %s", statenames[state])
        self._state = state

    def open_mode(self):
        self.set_state(OPEN_MODE)
        self._timeout = None
        self._door_io.led_on()
        self._door_io.granted()

    def await_rfid(self):
        self.set_state(AWAIT_RFID)
        self._timeout = None
        self._rfid = ''
        self._door_io.led_off()

    def await_pin(self):
        self.set_state(AWAIT_PIN)
        self._timeout = PIN_TIMEOUT
        self._pin = ''
        self._door_io.led_blink()

    def add_key(self):
        self.set_state(ADD_KEY)
        self._timeout = PIN_TIMEOUT
        self._rfid = ''
        self._door_io.led_blink()

    def add_key_pin_new(self):
        self.set_state(ADD_KEY_PIN_NEW)
        self._timeout = PIN_TIMEOUT
        self._pin = ''
        self._door_io.led_blink()

    def add_key_pin_verify(self):
        self.set_state(ADD_KEY_PIN_VERIFY)
        self._timeout = PIN_TIMEOUT
        self._orig_pin = self._pin
        self._pin = ''
        self._door_io.led_blink()

    def reset_pin(self):
        self.set_state(RESET_PIN)
        self._timeout = PIN_TIMEOUT
        self._rfid = ''
        self._door_io.led_blink()

    def pinchange_old(self):
        self.set_state(PINCHANGE_OLD)
        self._timeout = PIN_TIMEOUT
        self._pin = ''
        self._door_io.led_blink()

    def pinchange_new(self):
        self.set_state(PINCHANGE_NEW)
        self._timeout = PIN_TIMEOUT
        self._pin = ''
        self._door_io.led_blink()

    def pinchange_verify(self):
        self.set_state(PINCHANGE_VERIFY)
        self._timeout = PIN_TIMEOUT
        self._orig_pin = self._pin
        self._pin = ''
        self._door_io.led_blink()

    def do_open(self):
        self.set_state(OPEN)
        self._timeout = UNLOCK_TIMEOUT
        self._door_io.led_on()
        self._door_io.unlock()
        self._door_io.granted()
        self._pin = ''

    def relock(self):
        self.set_state(RELOCK)
        self._timeout = RELOCK_TIMEOUT
        self._door_io.led_off()
        self._door_io.lock()

    # events

    def door_open(self):
        log.info("door open")
        if self._state not in (OPEN_MODE, OPEN, RELOCK):
            log.warning("unauthorized access??")
        if self._state == OPEN:
            self.relock()

    @staticmethod
    def door_closed():
        log.info("door closed")

    def denied(self):
        self._door_io.denied()
        self.await_rfid()

    def pin_entered(self):
        if self._state == AWAIT_PIN:
            if self._pin == '999':
                self.pinchange_old()
            else:
                user_data = userdb.verify_login(self._dbconn, self._rfid, self._pin)
                if user_data is not None:
                    log.info("Authentication successful")
                    log.debug("rfid = %s", user_data['rfid'])
                    self.do_open()
                else:
                    log.info("Authentication failed")
                    self.denied()

        elif self._state == PINCHANGE_OLD:
            user_data = userdb.verify_login(self._dbconn, self._rfid, self._pin)
            if user_data is not None:
                self.pinchange_new()
            else:
                self.denied()

        elif self._state == PINCHANGE_NEW:
            if len(self._pin) >= 4:
                self.pinchange_verify()
            else:
                self.denied()

        elif self._state == PINCHANGE_VERIFY:
            if self._pin == self._orig_pin:
                log.info("Changing pin")
                userdb.update_pin(self._dbconn, self._rfid, self._pin)
                self.await_rfid()
                self._door_io.granted()
            else:
                self.denied()

        elif self._state == ADD_KEY_PIN_NEW:
            if len(self._pin) >= 4:
                self.add_key_pin_verify()
            else:
                self.denied()

        elif self._state == ADD_KEY_PIN_VERIFY:
            if self._pin == self._orig_pin:
                log.info("Adding key")
                userdb.add_user(self._dbconn, self._rfid, self._pin, 1)
                self.await_rfid()
                self._door_io.granted()
            else:
                self.denied()

    def key_pressed(self, c):
        log.debug("key pressed: %s", c)
        if self._state == OPEN_MODE:
            if c == "B":
                self._door_io.beep()
                self._door_io.unlock()

        elif self._state in (AWAIT_PIN, ADD_KEY_PIN_NEW, ADD_KEY_PIN_VERIFY, PINCHANGE_OLD, PINCHANGE_NEW,
                             PINCHANGE_VERIFY):
            self._timeout = PIN_TIMEOUT
            if c in "0123456789CB":
                self._door_io.beep()

                if c in "0123456789":
                    self._pin += c
                elif c == "C":
                    self._pin = ''
                elif c == "B":
                    self.pin_entered()

    def rfid_scanned(self, code):
        if self._state == RELOCK:
            self.await_rfid()

        log.debug("rfid code: %s", code)

        if self._state == AWAIT_RFID:
            self._rfid = code
            self.await_pin()
        elif self._state == ADD_KEY:
            if not userdb.user_exists(self._dbconn, code):
                self._rfid = code
                self.add_key_pin_new()
            else:
                self.denied()
        elif self._state == RESET_PIN:
            self._rfid = code
            self.pinchange_new()

    def timeout(self):
        log.debug("timeout")
        if self._state in (AWAIT_PIN, ADD_KEY, RESET_PIN, ADD_KEY_PIN_NEW, ADD_KEY_PIN_VERIFY, PINCHANGE_OLD,
                           PINCHANGE_NEW, PINCHANGE_VERIFY):
            self.denied()
        if self._state == RELOCK:
            self.await_rfid()
        if self._state == OPEN:
            self.relock()

    def run(self):
        self.await_rfid()
        start = 0.
        while True:
            if self._timeout is not None:
                start = time.time()

            event = self._door_io.get_event(self._timeout)

            if self._timeout is not None:
                self._timeout -= time.time() - start
                if self._timeout <= 0:
                    self._timeout = None
                    self.timeout()

            t = event['type']
            value = event.get('value', '')

            if t == 'doorstate':
                if value == 'OPEN':
                    self.door_open()
                if value == 'CLOSED':
                    self.door_closed()
            elif t == 'keypress':
                self.key_pressed(value)
            elif t == 'rfid':
                self.rfid_scanned(value)
            elif t == 'addkey':
                self.add_key()
            elif t == 'openmode':
                self.open_mode()
            elif t == 'authmode':
                self.relock()
            elif t == 'resetpin':
                self.reset_pin()
            elif t == 'shutdown':
                return True
            elif t == 'restart':
                return False
