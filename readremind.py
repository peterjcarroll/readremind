from datetime import datetime, timedelta
import json
import os.path
import RPi.GPIO as GPIO
import time
import http.client, urllib
from secrets import PUSHOVER_APP_TOKEN, PUSHOVER_USER_TOKEN


# notification constants
NOTIF_NO_READ_HOURS = 24
NOTIF_READ_MINUTES = 120
NOTIF_PROXIMITY = 20 # centimeters the book should be within
NOTIF_MIN_NAG_MINUTES = 60

PERSIST_JSON_FILE = 'bookstate.json'

# contants for GPIO pins
TRIG = 23
ECHO = 24
LED1 = 17
LED2 = 27

# state
class BookState():
    is_book_present = False
    last_state_change = datetime.min
    last_nag_notif = datetime.min

    def nag_check(self):
        time_since_last_nag = datetime.now() - self.last_nag_notif
        if time_since_last_nag < timedelta(minutes=NOTIF_MIN_NAG_MINUTES):
            return # It's too soon since the last nag

        time_in_state = datetime.now() - self.last_state_change
        if self.is_book_present and time_in_state > timedelta(hours=NOTIF_NO_READ_HOURS):
            send_notification(f"You haven't picked up your book for {time_in_state}. Time to read!")
        elif not self.is_book_present and time_in_state > timedelta(minutes=NOTIF_READ_MINUTES):
            send_notification(f"Have you really been reading for {time_in_state}? Right on!")
        
        self.last_nag_notif = datetime.now()
        self.persist()


    def update(self, is_present_now:bool):
        if is_present_now == self.is_book_present:
            self.nag_check()
            return # state did not change
        
        self.is_book_present = is_present_now
        prev_state_change = self.last_state_change
        self.last_state_change = datetime.now()
        prev_state_duration = self.last_state_change - prev_state_change
        self.persist()
        self.update_presence_led()

        if self.is_book_present:
            send_notification(f'Book was set down after {prev_state_duration}')
        else:
            send_notification(f'Book was picked up after {prev_state_duration}')
        

    def persist(self):
        state = {}
        state['is_book_present'] = self.is_book_present
        state['last_state_change'] = self.last_state_change.isoformat()
        state['last_nag_notif'] = self.last_nag_notif.isoformat()
        with open(PERSIST_JSON_FILE, 'w') as state_file:
            json.dump(state, state_file, indent=4)


    def restore(self):
        if os.path.exists(PERSIST_JSON_FILE):
            with open(PERSIST_JSON_FILE, 'r') as state_file:
                state = json.load(state_file)
                self.is_book_present = state['is_book_present']
                self.last_state_change = datetime.fromisoformat(state['last_state_change'])
                self.last_nag_notif = datetime.fromisoformat(state['last_nag_notif'])


    def update_presence_led(self):
        if self.is_book_present:
            GPIO.output(LED2, GPIO.HIGH)
        else:
            GPIO.output(LED2, GPIO.LOW)


def send_notification(msg:str):
    print(msg)
    conn = http.client.HTTPSConnection("api.pushover.net:443")
    conn.request("POST", "/1/messages.json",
    urllib.parse.urlencode({
        "token": PUSHOVER_APP_TOKEN,
        "user": PUSHOVER_USER_TOKEN,
        "message": msg,
    }), { "Content-type": "application/x-www-form-urlencoded" })
    conn.getresponse()


def proximity_setup():
    print("Distance Measurement in Progress")

    GPIO.setup(TRIG,GPIO.OUT)
    GPIO.setup(ECHO,GPIO.IN)

    GPIO.output(TRIG, False)
    print("Waiting For Sensor To Settle")
    time.sleep(2)


def get_proximity() -> float:
    # trigger the sensor
    GPIO.output(TRIG, True)
    time.sleep(0.00001)
    GPIO.output(TRIG, False)

    while GPIO.input(ECHO)==0:
        pulse_start = time.time()

    while GPIO.input(ECHO)==1:
        pulse_end = time.time() 

    pulse_duration = pulse_end - pulse_start
    distance = pulse_duration * 17150
    distance = round(distance, 2)
    return distance


def led_setup():
    GPIO.setup(LED1, GPIO.OUT)
    GPIO.setup(LED2, GPIO.OUT)
    # turn on LED1 as an indicator that the program is running
    GPIO.output(LED1, GPIO.HIGH)


def led_cleanup():
    GPIO.output(LED1, GPIO.LOW)
    GPIO.output(LED2, GPIO.LOW)


def setup(state:BookState):
    state.restore()
    GPIO.setmode(GPIO.BCM)
    led_setup()
    proximity_setup()    
    state.update_presence_led()


def cleanup():
    print("Cleaning up")
    led_cleanup()
    GPIO.cleanup()


def main_loop(state:BookState):
    distance = get_proximity()
    # print(f'Distance: {distance} cm')
    state.update(distance < NOTIF_PROXIMITY)


def main():
    try:
        state = BookState()
        setup(state)
        
        while True:
            main_loop(state)
            time.sleep(1)
    finally:
        cleanup()


if __name__ == '__main__':
    main()