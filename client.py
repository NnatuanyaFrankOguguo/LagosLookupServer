"""
Lagos Lookup Client

A menu-driven TCP client for the Lagos Lookup Server. It asks the user
what they want to look up, sends the request to the server as one line
of JSON, and prints the response as readable text.

Start server.py first, then run this file in a second terminal.
"""

import json
import socket
import sys

HOST = "localhost"
PORT = 5050
TIMEOUT_SECONDS = 10
CATEGORIES = ["hospital", "pharmacy", "fuel", "transport"]


class ServerConnection:
    """
    Wraps the TCP socket so the rest of the client only has to call
    send_request() and get a dictionary back.
    """

    def __init__(self, host, port):
        """
        Open a TCP connection to the server.

        Takes:   host (str), port (int) - where the server is listening.
        Returns: None.
        Raises:  ConnectionRefusedError if the server is not running.
        """
        self.sock = socket.create_connection((host, port), timeout=TIMEOUT_SECONDS)
        # makefile() gives us readline(), which reads up to the next "\n".
        # That is how we know where one JSON message ends and the next begins.
        self.reader = self.sock.makefile("r", encoding="utf-8")

    def send_request(self, request_type, value=None):
        """
        Send one request and wait for its one-line response.

        Takes:   request_type (str) - "LIST", "SEARCH", "NEAREST" or "STATS".
                 value (str or None) - the input for that request, if any.
        Returns: dict - the server's response. If the server sends back
                 something that is not valid JSON, an error dict is returned.
        Raises:  ConnectionError if the server has gone away.
        """
        request = {"type": request_type}
        if value is not None:
            request["value"] = value

        message = json.dumps(request) + "\n"
        self.sock.sendall(message.encode("utf-8"))

        line = self.reader.readline()
        if line == "":
            raise ConnectionError("The server closed the connection")

        try:
            response = json.loads(line)
        except json.JSONDecodeError:
            return {"status": "error", "message": "The server sent a reply that was not valid JSON"}

        if not isinstance(response, dict):
            return {"status": "error", "message": "The server sent a reply in an unexpected format"}

        return response

    def close(self):
        """
        Close the connection to the server.

        Takes:   nothing.
        Returns: None.
        """
        self.reader.close()
        self.sock.close()


# ---------------------------------------------------------------------------
# Getting input from the user
# ---------------------------------------------------------------------------

def print_menu():
    """
    Print the numbered main menu.

    Takes:   nothing.
    Returns: None.
    """
    print()
    print("=========== Lagos Lookup ===========")
    print("  1. List by category")
    print("  2. Search by name")
    print("  3. Find nearest")
    print("  4. Stats")
    print("  5. Quit")
    print("====================================")


def ask_category():
    """
    Ask the user which category to list.

    Takes:   nothing.
    Returns: str - the category typed (lower case), or None if left blank.
    """
    print("Categories: " + ", ".join(CATEGORIES))
    category = input("Enter a category: ").strip().lower()
    if category == "":
        print("Please type a category name.")
        return None
    return category


def ask_search_text():
    """
    Ask the user for text to search for in location names.

    Takes:   nothing.
    Returns: str - the search text, or None if left blank.
    """
    text = input("Enter part of a name (e.g. 'pharmacy', 'ikeja'): ").strip()
    if text == "":
        print("Search text cannot be empty.")
        return None
    return text


def ask_number(prompt, lowest, highest):
    """
    Ask the user for a number and check it is within a range.

    Takes:   prompt (str) - the question to show.
             lowest, highest (float) - the allowed range, inclusive.
    Returns: float - the number typed, or None if it was not valid.
    """
    text = input(prompt).strip()
    try:
        number = float(text)
    except ValueError:
        print(f"'{text}' is not a number.")
        return None

    if not (lowest <= number <= highest):
        print(f"The number must be between {lowest} and {highest}.")
        return None
    return number


def ask_coordinates():
    """
    Ask the user for a latitude and longitude.

    Takes:   nothing.
    Returns: str - "<lat> <lng>" ready to send, or None if either was invalid.
    """
    print("Tip: central Lagos is about latitude 6.5244, longitude 3.3792")
    lat = ask_number("Latitude:  ", -90, 90)
    if lat is None:
        return None
    lng = ask_number("Longitude: ", -180, 180)
    if lng is None:
        return None
    return f"{lat} {lng}"


# ---------------------------------------------------------------------------
# Showing responses
# ---------------------------------------------------------------------------

def format_location(location, number):
    """
    Turn one location record into a few lines of readable text. Phone and
    hours are optional in the data, so missing ones show as "Not listed".

    Takes:   location (dict) - one location from the server.
             number (int) - its position in the list, starting at 1.
    Returns: str - the formatted text.
    """
    name = location.get("name", "Unnamed location")
    category = location.get("category", "unknown")
    lines = [f"{number}. {name} [{category}]"]

    if "distance_km" in location:
        lines.append(f"     Distance: {location['distance_km']} km away")

    lines.append(f"     Address:  {location.get('address', 'Not listed')}")
    lines.append(f"     Phone:    {location.get('phone', 'Not listed')}")
    lines.append(f"     Hours:    {location.get('hours', 'Not listed')}")
    return "\n".join(lines)


def show_error(response):
    """
    Print an error response from the server.

    Takes:   response (dict) - a response whose status is "error".
    Returns: None.
    """
    print(f"Server error: {response.get('message', 'no details given')}")


def show_locations(response, heading):
    """
    Print a list of locations, or a friendly message if there are none.

    Takes:   response (dict) - the server's response.
             heading (str) - a title describing what was asked for.
    Returns: None.
    """
    if response.get("status") != "ok":
        show_error(response)
        return

    results = response.get("results", [])
    print()
    print(f"{heading} - {len(results)} result(s)")
    print("-" * 40)

    if len(results) == 0:
        print("No locations matched.")
        return

    number = 1
    for location in results:
        print(format_location(location, number))
        number += 1


def show_stats(response):
    """
    Print the per-category counts and the total.

    Takes:   response (dict) - the server's STATS response.
    Returns: None.
    """
    if response.get("status") != "ok":
        show_error(response)
        return

    print()
    print("Locations per category")
    print("-" * 40)
    categories = response.get("categories", {})
    for category, count in categories.items():
        print(f"  {category:<12} {count}")
    print("-" * 40)
    print(f"  {'total':<12} {response.get('total', 0)}")


# ---------------------------------------------------------------------------
# Menu actions - one function per menu option
# ---------------------------------------------------------------------------

def do_list(connection):
    """
    Menu option 1: list every location in a category.

    Takes:   connection (ServerConnection).
    Returns: None.
    """
    category = ask_category()
    if category is not None:
        response = connection.send_request("LIST", category)
        show_locations(response, f"Category: {category}")


def do_search(connection):
    """
    Menu option 2: search location names.

    Takes:   connection (ServerConnection).
    Returns: None.
    """
    text = ask_search_text()
    if text is not None:
        response = connection.send_request("SEARCH", text)
        show_locations(response, f"Names containing '{text}'")


def do_nearest(connection):
    """
    Menu option 3: find the 3 locations closest to a point.

    Takes:   connection (ServerConnection).
    Returns: None.
    """
    coordinates = ask_coordinates()
    if coordinates is not None:
        response = connection.send_request("NEAREST", coordinates)
        show_locations(response, f"Nearest to {coordinates}")


def do_stats(connection):
    """
    Menu option 4: show how many locations are in each category.

    Takes:   connection (ServerConnection).
    Returns: None.
    """
    response = connection.send_request("STATS")
    show_stats(response)


# Menu choice -> the function that carries it out (mirrors HANDLERS on the server).
MENU_ACTIONS = {
    "1": do_list,
    "2": do_search,
    "3": do_nearest,
    "4": do_stats,
}


def run_menu(connection):
    """
    Show the menu and carry out the user's choices until they quit or
    the connection to the server is lost.

    Takes:   connection (ServerConnection).
    Returns: None.
    """
    while True:
        print_menu()
        choice = input("Choose an option (1-5): ").strip()

        if choice == "5":
            print("Goodbye!")
            return

        action = MENU_ACTIONS.get(choice)
        if action is None:
            print(f"'{choice}' is not an option. Please enter a number from 1 to 5.")
            continue

        try:
            action(connection)
        except (ConnectionError, OSError):
            print()
            print("Lost connection to the server - it may have been stopped.")
            print("Restart it with 'python server.py', then run the client again.")
            return


def main():
    """
    Connect to the server and run the menu. Explains what to do if the
    server is not running.

    Takes:   nothing.
    Returns: None. Exits with status 1 if the server cannot be reached.
    """
    try:
        connection = ServerConnection(HOST, PORT)
    except ConnectionRefusedError:
        print(f"Could not connect to the server at {HOST}:{PORT}.")
        print("Start the server first in another terminal with: python server.py")
        sys.exit(1)
    except OSError as error:
        print(f"Could not connect to the server at {HOST}:{PORT}: {error}")
        sys.exit(1)

    print(f"Connected to Lagos Lookup Server at {HOST}:{PORT}")
    try:
        run_menu(connection)
    except (KeyboardInterrupt, EOFError):
        print()
        print("Goodbye!")
    finally:
        connection.close()


if __name__ == "__main__":
    main()
