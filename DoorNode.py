import cv2
import requests
import threading
import time
import numpy as np
from flask import Flask, request, jsonify

# Configuration
HUB_URL = "http://192.168.0.113:8080/hub"  # Hub address with /hub prefix
CAMERA_INDEX = 0  # Change this if you have multiple cameras

# Flask app to handle open signals
app = Flask(__name__)

# Open a connection to the camera
cap = cv2.VideoCapture(CAMERA_INDEX)

if not cap.isOpened():
    print("Error: Could not open camera.")
    exit()

# Door state
door_open = False

# Variable to store the door's unique ID (assigned by the hub)
door_id = None

# Global variable to store the timer thread
door_timer = None


def rgb_array_to_string(array):
    """
    Converts an OpenCV array to a compact string with hex values.

    Args:
    - array: A numpy array with shape (height, width, 3)

    Returns:
    - A compact string representation of the array where each RGB triplet is
      represented by six hex characters and rows are separated by ;
    """
    rows = []
    for row in array:
        row_str = []
        for pixel in row:
            hex_pixel = ''.join(f'{val:02X}' for val in pixel)
            row_str.append(hex_pixel)
        rows.append(''.join(row_str))
    return ';'.join(rows)


def request_door_id_from_hub():
    """Request a unique door ID from the central hub."""
    global door_id
    response = requests.get(f"{HUB_URL}/get_index")
    if response.status_code == 200:
        door_id = response.json().get("index")
        print(f"Received unique door ID {door_id} from the hub.")
    else:
        print(f"Failed to get door ID from the hub: {response.text}")
        exit()  # Exit if the door ID cannot be retrieved


def send_image_to_hub(frame):
    """Send the captured frame and door ID to the central hub."""
    # Resize frame to 1/4 size for faster processing
    small_frame = cv2.resize(frame, (0, 0), fx=0.25, fy=0.25)

    # Convert the frame to a compact string representation
    frame_string = rgb_array_to_string(small_frame)

    # Send the frame string and door ID to the hub
    response = requests.post(
        f"{HUB_URL}/receive_image",
        json={"image": frame_string, "door_id": door_id}
    )
    if response.status_code == 200:
        pass
        #print(f"Image sent successfully from door {door_id}.")
    else:
        pass
        #print(f"Failed to send image from door {door_id}: {response.text}")


def poll_for_open_signal():
    """Poll the hub to check if the door should open."""
    while True:
        response = requests.get(f"{HUB_URL}/should_open", params={"door_id": door_id})
        if response.status_code == 200:
            print(f"Received open signal from hub: {response.json().get('message')}")
            open_door()
        time.sleep(1)  # Poll every second


def open_door():
    """Open the door and refresh the timer."""
    global door_open, door_timer

    # Open the door if it's not already open
    if not door_open:
        door_open = True
        print(f"Door {door_id} opened.")

    # Refresh the timer
    refresh_timer()


def refresh_timer():
    """Refresh the timer to keep the door open for 10 seconds."""
    global door_timer

    # Cancel the existing timer if it exists
    if door_timer is not None:
        door_timer.cancel()

    # Start a new timer to close the door after 10 seconds
    door_timer = threading.Timer(10.0, close_door)
    door_timer.start()


def close_door():
    """Close the door."""
    global door_open, door_timer
    door_open = False
    door_timer = None
    print(f"Door {door_id} closed.")


# Request a unique door ID from the hub at the beginning
request_door_id_from_hub()

# Start a thread to poll for open signals
threading.Thread(target=poll_for_open_signal, daemon=True).start()

# Main loop to capture and send images
frame_counter = 0
while True:
    ret, frame = cap.read()
    if not ret:
        print("Error: Could not capture frame.")
        break

    frame_counter += 1
    if frame_counter % 6 == 0:  # Send every 6th frame
        threading.Thread(target=send_image_to_hub, args=(frame,)).start()

cap.release()