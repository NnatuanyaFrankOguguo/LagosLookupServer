"""
Lagos Lookup Server

A TCP server that answers lookup requests about essential services in
Lagos, Nigeria (hospitals, pharmacies, fuel stations and transport hubs).

Protocol: newline-delimited JSON. The client sends one JSON object per
line, and the server answers each one with exactly one JSON object on a
line of its own.

    Request:  {"type": "LIST", "value": "pharmacy"}
    Response: {"status": "ok", "count": 7, "results": [ ... ]}
    Error:    {"status": "error", "message": "Unknown category: clinic"}
"""

import json
import math
import os
import socketserver
import sys
from datetime import datetime

HOST = "localhost"
PORT = 5050

# Build the path from this file's folder so the server works no matter
# which folder it is started from.
DATA_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "locations.json")

VALID_CATEGORIES = ["hospital", "pharmacy", "fuel", "transport"]
REQUIRED_FIELDS = ["id", "name", "category", "lat", "lng"]
EARTH_RADIUS_KM = 6371.0
NEAREST_LIMIT = 3


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def log(message):
    """
    Print a message to the console with a timestamp in front of it.

    Takes:   message (str) - the text to print.
    Returns: None.
    """
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] {message}", flush=True)


def load_locations(file_path):
    """
    Read the locations dataset from a JSON file. Records that are missing
    a required field are skipped with a warning so one bad record cannot
    break the whole server.

    Takes:   file_path (str) - path to the JSON file.
    Returns: list of location dictionaries.
    Raises:  OSError if the file cannot be opened, ValueError if the file
             is not valid JSON or does not contain a list.
    """
    with open(file_path, "r", encoding="utf-8") as data_file:
        data = json.load(data_file)

    if not isinstance(data, list):
        raise ValueError("locations.json must contain a list of locations")

    locations = []
    for record in data:
        missing = []
        for field in REQUIRED_FIELDS:
            if field not in record:
                missing.append(field)

        if missing:
            log(f"WARNING: skipping record {record} - missing {missing}")
        else:
            locations.append(record)

    return locations


def make_ok(results):
    """
    Build a successful response that carries a list of results.

    Takes:   results (list) - the location dictionaries to send back.
    Returns: dict - {"status": "ok", "count": <n>, "results": [...]}.
    """
    return {"status": "ok", "count": len(results), "results": results}


def make_error(message):
    """
    Build an error response.

    Takes:   message (str) - a human-readable explanation of the problem.
    Returns: dict - {"status": "error", "message": <message>}.
    """
    return {"status": "error", "message": message}


def haversine_km(lat1, lng1, lat2, lng2):
    """
    Work out the distance between two points on the Earth's surface using
    the haversine formula, which accounts for the Earth being a sphere.

    Takes:   lat1, lng1 (float) - first point in decimal degrees.
             lat2, lng2 (float) - second point in decimal degrees.
    Returns: float - the distance in kilometres.
    """
    lat1_rad = math.radians(lat1)
    lat2_rad = math.radians(lat2)
    delta_lat = math.radians(lat2 - lat1)
    delta_lng = math.radians(lng2 - lng1)

    a = (math.sin(delta_lat / 2) ** 2
         + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(delta_lng / 2) ** 2)
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    return EARTH_RADIUS_KM * c


def parse_coordinates(value):
    """
    Turn the text "<lat> <lng>" into two numbers and check they are valid.

    Takes:   value - the "value" field from a NEAREST request.
    Returns: tuple (lat, lng) of floats.
    Raises:  ValueError with a message the client can show to the user.
    """
    if not isinstance(value, str):
        raise ValueError("Coordinates must be sent as text: \"<lat> <lng>\"")

    parts = value.split()
    if len(parts) != 2:
        raise ValueError("NEAREST needs exactly two values: <lat> <lng>")

    try:
        lat = float(parts[0])
        lng = float(parts[1])
    except ValueError:
        raise ValueError(f"Coordinates must be numbers, got: {value}")

    # "not (a <= x <= b)" also rejects nan, because comparisons with nan are False.
    if not (-90 <= lat <= 90):
        raise ValueError(f"Latitude must be between -90 and 90, got: {lat}")
    if not (-180 <= lng <= 180):
        raise ValueError(f"Longitude must be between -180 and 180, got: {lng}")

    return lat, lng


def get_distance(location):
    """
    Sort key used to order locations from nearest to farthest.

    Takes:   location (dict) - a location that already has "distance_km".
    Returns: float - that location's distance in kilometres.
    """
    return location["distance_km"]


# ---------------------------------------------------------------------------
# Request handlers - one function per request type
# ---------------------------------------------------------------------------

def handle_list(value, locations):
    """
    LIST <category>: return every location in one category.

    Takes:   value (str) - the category name, e.g. "pharmacy".
             locations (list) - the full dataset.
    Returns: dict - an ok response with the matches, or an error response
             if the category is not one we know about.
    """
    if not isinstance(value, str) or value.strip() == "":
        return make_error("LIST needs a category name")

    category = value.strip().lower()
    if category not in VALID_CATEGORIES:
        choices = ", ".join(VALID_CATEGORIES)
        return make_error(f"Unknown category: {value.strip()} (choose from {choices})")

    matches = []
    for location in locations:
        if location["category"] == category:
            matches.append(location)

    return make_ok(matches)


def handle_search(value, locations):
    """
    SEARCH <text>: return locations whose name contains the text,
    ignoring upper/lower case. Zero matches is a valid, successful answer.

    Takes:   value (str) - the text to look for.
             locations (list) - the full dataset.
    Returns: dict - an ok response with the matches (possibly empty), or an
             error response if the search text is empty.
    """
    if not isinstance(value, str) or value.strip() == "":
        return make_error("Search text cannot be empty")

    search_text = value.strip().lower()
    matches = []
    for location in locations:
        if search_text in location["name"].lower():
            matches.append(location)

    return make_ok(matches)


def handle_nearest(value, locations):
    """
    NEAREST <lat> <lng>: return the 3 closest locations to a point, each
    with a "distance_km" field rounded to 2 decimal places.

    Takes:   value (str) - the point as "<lat> <lng>", e.g. "6.5244 3.3792".
             locations (list) - the full dataset.
    Returns: dict - an ok response with up to 3 locations, nearest first,
             or an error response if the coordinates are invalid.
    """
    try:
        lat, lng = parse_coordinates(value)
    except ValueError as error:
        return make_error(str(error))

    ranked = []
    for location in locations:
        distance = haversine_km(lat, lng, location["lat"], location["lng"])
        # Copy the record so the dataset in memory is never changed.
        result = dict(location)
        result["distance_km"] = round(distance, 2)
        ranked.append(result)

    ranked.sort(key=get_distance)
    return make_ok(ranked[:NEAREST_LIMIT])


def handle_stats(value, locations):
    """
    STATS: count how many locations are in each category, plus a total.

    Takes:   value - ignored; STATS does not need any input.
             locations (list) - the full dataset.
    Returns: dict - {"status": "ok", "total": <n>, "categories": {...}}.
    """
    counts = {}
    for category in VALID_CATEGORIES:
        counts[category] = 0

    for location in locations:
        category = location["category"]
        if category in counts:
            counts[category] += 1
        else:
            counts[category] = 1

    return {"status": "ok", "total": len(locations), "categories": counts}


# The dispatch table: request type -> the function that answers it.
# Adding a new request type means writing one function and adding one line here.
HANDLERS = {
    "LIST": handle_list,
    "SEARCH": handle_search,
    "NEAREST": handle_nearest,
    "STATS": handle_stats,
}


def process_request(line, locations):
    """
    Turn one line of text from a client into one response. This is the
    single place where bad input is caught, so the server never crashes.

    Takes:   line (str) - one line received from the client.
             locations (list) - the full dataset.
    Returns: dict - the response to send back (ok or error).
    """
    try:
        request = json.loads(line)
    except json.JSONDecodeError:
        return make_error("Malformed JSON: the request could not be read")

    if not isinstance(request, dict):
        return make_error("A request must be a JSON object")

    request_type = request.get("type")
    if not isinstance(request_type, str) or request_type.strip() == "":
        return make_error("The request is missing a \"type\" field")

    request_type = request_type.strip().upper()
    handler = HANDLERS.get(request_type)
    if handler is None:
        return make_error(f"Unknown request type: {request_type}")

    value = request.get("value", "")
    try:
        return handler(value, locations)
    except Exception as error:
        # Last line of defence: a bug in a handler must not take the server down.
        log(f"ERROR while handling {request_type}: {error!r}")
        return make_error("The server hit an internal error handling that request")


# ---------------------------------------------------------------------------
# Networking
# ---------------------------------------------------------------------------

class LookupRequestHandler(socketserver.StreamRequestHandler):
    """
    Handles one connected client. socketserver creates a new instance of
    this class (on its own thread) for every client that connects.
    """

    def handle(self):
        """
        Read requests from the client one line at a time and answer each
        one, until the client disconnects.

        Takes:   nothing (the socket is available as self.rfile / self.wfile).
        Returns: None.
        """
        client = f"{self.client_address[0]}:{self.client_address[1]}"
        log(f"Client connected: {client}")

        while True:
            try:
                raw_line = self.rfile.readline()
            except ConnectionError:
                break

            # An empty read means the client closed the connection.
            if not raw_line:
                break

            line = raw_line.decode("utf-8", errors="replace").strip()
            if line == "":
                continue

            log(f"{client} request:  {line}")
            response = process_request(line, self.server.locations)
            log(f"{client} response: status={response['status']}")

            try:
                self.send_response(response)
            except ConnectionError:
                break

        log(f"Client disconnected: {client}")

    def send_response(self, response):
        """
        Send one response to the client as a single line of JSON.

        Takes:   response (dict) - the response to send.
        Returns: None.
        """
        message = json.dumps(response) + "\n"
        self.wfile.write(message.encode("utf-8"))
        self.wfile.flush()


class LookupServer(socketserver.ThreadingTCPServer):
    """
    A threaded TCP server that also holds the dataset, so every handler
    can reach it through self.server.locations.
    """

    # Lets the server restart straight away without "address already in use".
    allow_reuse_address = True
    # Client threads stop automatically when the server shuts down.
    daemon_threads = True

    def __init__(self, address, handler_class, locations):
        """
        Create the server and store the dataset on it.

        Takes:   address (tuple) - (host, port) to listen on.
                 handler_class - the class used to handle each client.
                 locations (list) - the dataset loaded at startup.
        Returns: None.
        """
        self.locations = locations
        super().__init__(address, handler_class)


def main():
    """
    Load the dataset once, then start the server and run until Ctrl+C.

    Takes:   nothing.
    Returns: None. Exits with status 1 if the data or port is unusable.
    """
    try:
        locations = load_locations(DATA_FILE)
    except (OSError, ValueError) as error:
        print(f"Could not load {DATA_FILE}: {error}")
        sys.exit(1)

    log(f"Loaded {len(locations)} locations from {os.path.basename(DATA_FILE)}")

    try:
        server = LookupServer((HOST, PORT), LookupRequestHandler, locations)
    except OSError as error:
        print(f"Could not start the server on port {PORT}: {error}")
        print("Is another copy of the server already running?")
        sys.exit(1)

    with server:
        log(f"Lagos Lookup Server listening on {HOST}:{PORT} (Ctrl+C to stop)")
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            log("Shutting down")


if __name__ == "__main__":
    main()
