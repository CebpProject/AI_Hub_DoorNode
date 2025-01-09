import json
import datetime
from flask import Flask, jsonify, request
import cv2
import face_recognition
import threading
import numpy as np
import requests
from io import BytesIO

app = Flask(__name__)

thread_complete_event = threading.Event()

# Dictionary to store counts for each door
door_counts = {}

def rgb_array_to_string(array):
    """
    Converts an OpenCV array to a compact string with hex values.

    Args:
    - array: A numpy array with shape (height, width, 3)

    Returns:
    - A compact string representation of the array where each RGB triplet is
      represented by six hex characters and rows are separated by two characters.
    """
    rows = []
    for row in array:
        row_str = []
        for pixel in row:
            hex_pixel = ''.join(f'{val:02X}' for val in pixel)
            row_str.append(hex_pixel)
        rows.append(''.join(row_str))
    return ';'.join(rows)

def string_to_rgb_array(s):
    """
    Converts a compact string with hex values back to an OpenCV array.

    Args:
    - s: A compact string representation of the array where each RGB triplet is
         represented by six hex characters and rows are separated by two characters.

    Returns:
    - A numpy array with shape (height, width, 3)
    """
    # Split the string by ';' to get each row
    rows = s.split(';')

    # Convert each row to a list of pixels
    pixels = []
    for row in rows:
        pixel_row = [list(int(row[i:i + 2], 16) for i in range(j, j + 6, 2)) for j in range(0, len(row), 6)]
        pixels.append(pixel_row)

    # Convert pixels to a numpy array
    return np.array(pixels, dtype=np.uint8)

# Load known images and encode them
known_face_encodings = []
known_face_names = []

def load_known_faces():
    """
    Load known face images and names from a remote source.
    """
    url = "http://192.168.0.197:8080/api/groundTruthPhotos"
    response = requests.get(url)
    if response.status_code == 200:
        data = response.json()
        for person in data:
            image_data = string_to_rgb_array(person['photoList'])
            name = person['name']
            image_encoding = face_recognition.face_encodings(image_data)[0]
            known_face_encodings.append(image_encoding)
            known_face_names.append(name)
        print("Done getting images")
    else:
        print("Failed to fetch known faces. Status code:", response.status_code)

# Load known faces initially
load_known_faces()

def process_single_frame(frame, doorId):
    """
    Process a single frame for face detection and recognition.

    Args:
    - frame: The frame to process.
    - doorId: The ID of the door associated with the camera (integer).
    """
    global door_counts

    # Initialize counts for the door if not already done
    if doorId not in door_counts:
        door_counts[doorId] = {
            'nrOfFramesWithDetectedFaces': 0,
            'nrOfFramesWithRecognizedFaces': 0
        }

    face_detected = False
    face_recognized = False
    foundOne = False
    listOfRecognizedPeople = []

    # Find all face locations and face encodings in the current frame of video
    face_locations = face_recognition.face_locations(frame)

    if len(face_locations) > 0:
        face_detected = True
        door_counts[doorId]['nrOfFramesWithDetectedFaces'] += 1
    else:
        door_counts[doorId]['nrOfFramesWithDetectedFaces'] = 0

    face_encodings = face_recognition.face_encodings(frame, face_locations)

    face_names = []
    for face_encoding in face_encodings:
        # Check if the face matches any known faces
        matches = face_recognition.compare_faces(known_face_encodings, face_encoding)
        name = "Unknown"

        # If a match is found, use the name of the known face
        if True in matches:
            foundOne = True
            face_recognized = True
            door_counts[doorId]['nrOfFramesWithRecognizedFaces'] += 1
            first_match_index = matches.index(True)
            name = known_face_names[first_match_index]
            listOfRecognizedPeople.append(name)

        face_names.append(name)

    if not foundOne:
        door_counts[doorId]['nrOfFramesWithRecognizedFaces'] = 0

    # Display the results
    for (top, right, bottom, left), name in zip(face_locations, face_names):
        # Draw a rectangle around the face
        cv2.rectangle(frame, (left, top), (right, bottom), (0, 0, 255), 2)

        # Draw a label with a name below the face
        cv2.rectangle(frame, (left, bottom), (right, bottom), (0, 0, 255), cv2.FILLED)
        font = cv2.FONT_HERSHEY_DUPLEX
        cv2.putText(frame, name, (left + 6, bottom - 6), font, 0.5, (255, 255, 255), 1)

    data = {
        "dateTime": datetime.datetime.now().strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + 'Z',
        "faceDetected": face_detected,
        "faceRecognized": face_recognized,
        "recognizedPeople": listOfRecognizedPeople,
        "nrOfPastFramesWithDetection": door_counts[doorId]['nrOfFramesWithDetectedFaces'],
        "nrOfPastFramesWithRecognition": door_counts[doorId]['nrOfFramesWithRecognizedFaces'],
        "doorId": doorId  # Include doorId in the response (integer)
    }

    response = requests.post("http://192.168.0.197:8080/api/procesedImageOutput", json=data)

    thread_complete_event.set()
    cv2.imshow('Single Frame', frame)
    cv2.waitKey(0)
    cv2.destroyAllWindows()

def fetch_frame_from_url(url):
    try:
        response = requests.get(url)
        if response.status_code == 200:
            data = json.loads(response.content)
            return data.get("photoList")
        else:
            return None
    except Exception as e:
        return None

@app.route('/sync', methods=['GET'])
def sync():
    doorId = request.args.get('doorId', type=int)  # Parse doorId as an integer

    if doorId is None:
        return jsonify(message="doorId is required"), 400

    url = "http://192.168.0.197:8080/api/unprocesedImageInput"
    frameString = fetch_frame_from_url(url)
    if frameString is not None:
        # Reset the threading event before starting a new thread
        thread_complete_event.clear()

        # Start a new thread
        threading.Thread(target=process_single_frame, args=(string_to_rgb_array(frameString).copy(), doorId)).start()

        # Wait for the thread to complete its work before sending the response
        thread_complete_event.wait()

        return jsonify(message="Face recognition completed for a single frame"), 200
    else:
        return jsonify(message="Failed to fetch frame"), 500

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)