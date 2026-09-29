# Overview

Lagos Lookup Server is a TCP client-server application, written in Python, that
answers questions about essential services in Lagos, Nigeria. The server holds a
dataset of 28 hospitals, pharmacies, fuel stations and transport hubs, and it
answers lookup requests from any client that connects to it. The client is a
simple terminal menu: the user picks what they want to find, the client sends a
request over the network, and it prints the server's answer as readable text.

The server supports four kinds of request:

- **LIST** – every location in a category (hospital, pharmacy, fuel, transport)
- **SEARCH** – locations whose name contains some text, ignoring case
- **NEAREST** – the three locations closest to a latitude/longitude, using the
  haversine formula, with each distance in kilometres
- **STATS** – how many locations are in each category, plus a total

To use it, start the server in one terminal (`python server.py`), then start the
client in a second terminal (`python client.py`) and choose options from the menu.

My goal as a software engineer was to understand how two separate programs talk
to each other over a network: how a server listens on a port and serves several
clients at once, how a client connects and exchanges messages, and how to design
a small message protocol that both sides agree on. I especially wanted to learn
how to deal with the fact that TCP is a stream of bytes rather than a series of
separate messages, and how to make both programs keep running sensibly when the
other side sends bad data or disappears.

[Software Demo Video](http://youtube.link.goes.here)

# Network Communication

The software uses a **client-server** architecture. `server.py` owns the data and
does all the searching and distance calculations; `client.py` only collects input,
sends requests and displays results. The server uses Python's
`socketserver.ThreadingTCPServer`, so each connected client is handled on its own
thread and several clients can use the server at the same time.

Communication uses **TCP** on **port 5050** (both programs run on `localhost`).
TCP was chosen because every request must arrive complete and in order, and each
request needs exactly one reply.

Messages are **newline-delimited JSON**: every message is a single JSON object
followed by `\n`. Because TCP does not preserve message boundaries, the newline is
what tells the receiver where one message ends and the next begins. Each side
reads one line, then parses it as JSON.

Request format:

```json
{"type": "LIST", "value": "pharmacy"}
{"type": "SEARCH", "value": "ikeja"}
{"type": "NEAREST", "value": "6.5244 3.3792"}
{"type": "STATS"}
```

Successful response (LIST, SEARCH, NEAREST):

```json
{"status": "ok", "count": 7, "results": [ {"id": 8, "name": "...", "category": "pharmacy", "lat": 6.6143, "lng": 3.358, "address": "...", "phone": "...", "hours": "..."} ]}
```

NEAREST results also carry `"distance_km"` (rounded to 2 decimals). STATS replies
with `{"status": "ok", "total": 28, "categories": {"hospital": 7, ...}}`.

Error response (unknown request type, unknown category, empty search text,
non-numeric coordinates, malformed JSON, and so on):

```json
{"status": "error", "message": "Unknown category: clinic"}
```

The server never crashes on bad input; it always answers with an error message.

# Development Environment

- **Visual Studio Code** as the editor, with two integrated terminals (one for the
  server, one for the client)
- **Python 3**
- **Python standard library only** – `socket`, `socketserver`, `json`, `math`,
  `sys`, plus `os` (to locate the data file) and `datetime` (for log timestamps).
  No third-party packages are needed.

# Useful Websites

- [Python `socket` documentation](https://docs.python.org/3/library/socket.html)
- [Python `socketserver` documentation](https://docs.python.org/3/library/socketserver.html)
- [Python `json` documentation](https://docs.python.org/3/library/json.html)
- [OSI model (Wikipedia)](https://en.wikipedia.org/wiki/OSI_model)
- [Client-server model (Wikipedia)](https://en.wikipedia.org/wiki/Client%E2%80%93server_model)
- [Haversine formula (Wikipedia)](https://en.wikipedia.org/wiki/Haversine_formula)
- [Calculate distance between latitude/longitude points (Movable Type Scripts)](https://www.movable-type.co.uk/scripts/latlong.html)

# Future Work

- **Filter NEAREST by category** – let the user ask for "the nearest pharmacy" or
  "the nearest fuel station" instead of the nearest location of any type, which is
  what someone in an emergency actually needs.
- **Run across a real network** – make the host and port command-line arguments so
  the server can run on one machine and clients on others, and add automatic
  reconnection in the client when the server restarts.
- **Keep the data up to date** – add ADD and UPDATE request types (protected by a
  simple password) so new locations and changed opening hours can be sent to the
  server and saved back to `locations.json`, instead of editing the file by hand.
