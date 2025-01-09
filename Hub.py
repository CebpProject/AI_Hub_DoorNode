import datetime
from flask import Flask, request, jsonify
import requests
import threading
import time

app = Flask(__name__)

# In-memory storage for the next available door index
next_index = 0  # Tracks the next available index for a new door

# List to store the IP addresses of doors
door_ips = []  # Index corresponds to door index

# Dictionary to track open requests for each door
door_open_requests = {}  # door_id -> boolean

# Configuration
GET_OPEN_SIGNAL_URL = "http://192.168.0.197:8080/api/procesedImageOutput/getOpenSignal"


def poll_open_signal():
    """
    Continuously polls the external API for an open signal.
    If a 200 response is received with a door ID, marks the door for opening.
    """
    while True:
        response = requests.get(GET_OPEN_SIGNAL_URL)
        if response.status_code == 200:
            door_id_to_open = int(response.text)  # Response is just an integer (door_id)
            if door_id_to_open < len(door_ips):  # Check if the door exists
                door_open_requests[door_id_to_open] = True
                print(f"Received open signal for door {door_id_to_open}.")
            else:
                print(f"Received open signal for unknown door ID: {door_id_to_open}")
        time.sleep(1)  # Polling interval


# Start a thread to poll for open signals
threading.Thread(target=poll_open_signal, daemon=True).start()


@app.route('/hub/get_index', methods=['GET'])
def get_index():
    global next_index
    # Get the IP address of the door making the request
    door_ip = request.remote_addr

    # Assign the current next_index to the door
    assigned_index = next_index
    # Increment next_index for the next door
    next_index += 1

    # Store the door's IP address in the list
    if assigned_index >= len(door_ips):
        door_ips.append(door_ip)  # Add a new entry if the index is out of bounds
    else:
        door_ips[assigned_index] = door_ip  # Update existing entry

    # Initialize the open request for this door
    door_open_requests[assigned_index] = False
    requests.post("http://192.168.0.197:8080/api/doors/number-of-doors-to-open", json={"nrOfDoors": next_index})
    print(f"Assigned index {assigned_index} to door at {door_ip}.")
    return jsonify({"index": assigned_index}), 200


@app.route('/hub/should_open', methods=['GET'])
def should_open():
    """Respond to doors asking if they should open."""
    door_id = int(request.args.get("door_id", -1))
    if door_id in door_open_requests and door_open_requests[door_id]:
        # Clear the open request after acknowledging it
        door_open_requests[door_id] = False
        return jsonify({"message": f"Door {door_id} should open."}), 200
    return '', 204  # No content, door remains closed


def get_image_processing_status(door_id):
    response = requests.get('http://192.168.0.113:5000/sync', params={"doorId": door_id})
    return response


@app.route('/hub/receive_image', methods=['POST'])
def receive_image():
    global next_index
    data = request.json
    door_id = data.get('door_id')  # door_id is an integer
    image_string = data.get('image')

    # Log the received image
    # print(f"Received image from door {door_id}.")
    data = {
        'photoList': None,
        'dateTime': None,
        'doorId': door_id
    }

    data.update({'dateTime': datetime.datetime.now().strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + 'Z'})
    data.update({'photoList': image_string})

    requests.post("http://192.168.0.197:8080/api/unprocesedImageInput", json=data, verify=True)
    get_image_processing_status(door_id)

    # Respond with success
    return jsonify({"status": "success"}), 200


if __name__ == '__main__':
    requests.post("http://192.168.0.197:8080/api/doors/number-of-doors-to-open", json={"nrOfDoors": 1})
    print("Hub running. Listening for door connections...")
    app.run(host='0.0.0.0', port=8080)