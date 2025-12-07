"""This file provides a websocket server that can send notifications
to the frontend. Below is the format that the frontend can
expect to receive data in:

sonner (notification):
{
    "text": "This is a notification",
    "type": "info | warning | error | success",
    "promise": "promiseId" # NOTE: Promise is deprecated!
}

ask (question):
{
    "ask": {
        "text": "What is your name?",
        "options": ["John", "Doe"],
        "description": "Please select your name."
    }
}

ask (response from frontend):
{
    "response": "John"
}

navigate (navigate):
{
    "page": "url/to/the/page"
}

dialog (open dialog):
{
    "dialog": {
        "json": {}
    }
}
"""

from ETS2LA.Utils.translator import _
from ETS2LA.Handlers import sounds

from typing import Literal
import logging
import json

import websockets
import threading
import asyncio

connected = {}
"""
Connected websockets and their messages.
```
{
    websocket: message
}
```
"""

condition = threading.Condition()
"""Threading condition to wait for a response"""

# Persistent event loop for sync wrappers (avoids creating/destroying loops)
_loop: asyncio.AbstractEventLoop | None = None
_loop_lock = threading.Lock()

def _get_or_create_loop() -> asyncio.AbstractEventLoop:
    """Get or create a persistent event loop for sync operations."""
    global _loop
    with _loop_lock:
        if _loop is None or _loop.is_closed():
            _loop = asyncio.new_event_loop()
            # Start loop in background thread
            def run_loop():
                asyncio.set_event_loop(_loop)
                _loop.run_forever()
            threading.Thread(target=run_loop, daemon=True).start()
        return _loop

def _run_async(coro):
    """Run an async coroutine using the persistent event loop."""
    loop = _get_or_create_loop()
    future = asyncio.run_coroutine_threadsafe(coro, loop)
    return future.result(timeout=30)  # 30 second timeout


async def server(websocket, path) -> None:
    """The main websocket server that listens for client's
    messages. Please note that this server is called
    for every new connection!

    :param websocket: The websocket object (filled by websockets)
    :param path: The path that the client (filled by websockets)
    """
    global connected
    connected[websocket] = None
    try:
        while True:
            # Blocking until a message is received
            # or the connection is closed.
            try:
                message = await websocket.recv()
            except Exception:
                break

            # Handle the message
            if message is not None:
                try:
                    message = json.loads(message)
                except Exception:
                    pass

                with condition:
                    connected[websocket] = message
                    condition.notify_all()
    except Exception:
        logging.exception(_("An error occurred while processing a message."))
        pass

    finally:
        # Remove the websocket from the connected list
        connected.pop(websocket, None)


async def send_sonner(
    text: str,
    type: Literal["info", "warning", "error", "success", "promise"] = "info",
    sonner_promise: str | None = None,
) -> None:
    """Will send a notification to all connected clients.
    This function is blocking until all messages are sent.

    :param str text: The text of the notification
    :param str type: The type of the notification
    :param str sonner_promise: The promise ID (deprecated)
    """
    global connected
    message_dict = {"text": text, "type": type, "promise": sonner_promise}

    message = json.dumps(message_dict)
    tasks = [ws.send(message) for ws in connected]
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)


def sonner(
    text: str,
    type: Literal["info", "warning", "error", "success", "promise"] = "info",
    sonner_promise: str | None = None,
) -> None:
    """Blocking non-async function that will send a notification to all connected clients."""
    try:
        _run_async(send_sonner(text, type, sonner_promise))
    except Exception:
        logging.debug("Failed to send sonner notification")


async def send_ask(text: str, options: list[str], description: str) -> dict | None:
    """Will send a dialog with a question with the given options.
    This function is blocking until a response is received (with timeout).

    :param str text: The text of the question
    :param list[str] options: The options to choose from
    :param str description: The description of the question

    :return dict | None: The response from the client, or None on timeout
    """
    global connected
    message_dict = {
        "ask": {"text": text, "options": options, "description": description}
    }

    message = json.dumps(message_dict)

    tasks = [ws.send(message) for ws in connected]
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)

    # Wait for a response with timeout to prevent deadlock
    response = None
    timeout_seconds = 60  # 60 second timeout for user response
    start_time = asyncio.get_event_loop().time()

    while response is None:
        with condition:
            # Wait with 1 second timeout to allow checking total elapsed time
            condition.wait(timeout=1.0)
            for ws in connected:
                response = connected[ws]
                if response is not None:
                    connected[ws] = None
                    break

        # Check if we've exceeded the total timeout
        if asyncio.get_event_loop().time() - start_time > timeout_seconds:
            logging.warning("Timed out waiting for user response")
            return None

    return response


def ask(text: str, options: list, description: str = "") -> dict | None:
    """Non-async function that will send a dialog with a question with the given options."""
    sounds.Play("prompt")
    try:
        response = _run_async(send_ask(text, options, description))
        return response
    except Exception:
        logging.warning("Failed to get user response")
        return None


async def send_navigate(url: str, sender: str, reason: str = "") -> None:
    """Send a command to the frontend to navigate to a new page.

    :param str url: The page to navigate to.
    """
    global connected
    message_dict = {"navigate": {"url": url, "reason": reason, "sender": sender}}

    message = json.dumps(message_dict)
    tasks = [ws.send(message) for ws in connected]
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)


def navigate(url: str, sender: str, reason: str = "") -> None:
    """Non-async function that will send a command to the frontend to navigate to a new page."""
    if url == "":
        logging.error(_("Tried to send an empty page."))
        return
    try:
        _run_async(send_navigate(url, sender, reason))
    except Exception:
        logging.debug("Failed to send navigation command")


async def send_dialog(json_data: dict, no_response: bool = False) -> dict | None:
    """Send a dialog with the given json data to all connected clients.
    Will wait for a response if no_response is False (with timeout).

    :param dict json_data: The JSON data to send to the dialog
    :param bool no_response: If True, this function will not wait for a response.

    :return dict | None: The response from the client, or None on timeout
    """
    global connected
    message_dict = {"dialog": {"json": json_data}}

    message = json.dumps(message_dict)
    tasks = [ws.send(message) for ws in connected]
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)

    # Wait for a response from all connected clients with timeout
    response = None
    if not no_response:
        timeout_seconds = 60  # 60 second timeout for user response
        start_time = asyncio.get_event_loop().time()

        while response is None:
            with condition:
                # Wait with 1 second timeout to allow checking total elapsed time
                condition.wait(timeout=1.0)
                for ws in connected:
                    response = connected[ws]
                    if response is not None:
                        connected[ws] = None
                        break

            # Check if we've exceeded the total timeout
            if asyncio.get_event_loop().time() - start_time > timeout_seconds:
                logging.warning("Timed out waiting for dialog response")
                return None

    return response


def dialog(ui: dict, no_response: bool = False) -> dict | None:
    """Non-async function that will send a dialog with the given json data to all connected clients.

    :param dict ui: The JSON data to send to the dialog
    :param bool no_response: If True, this function will not wait for a response.

    :return dict | None: The response from the client
    """
    sounds.Play("prompt")
    try:
        response = _run_async(send_dialog(ui, no_response))
        return response
    except Exception:
        logging.warning("Failed to get dialog response")
        return None


async def start() -> None:
    """Serve the websocket server on 0.0.0.0 and port 37521."""
    wsServer = websockets.serve(server, "0.0.0.0", 37521, logger=logging.Logger("null"))
    await wsServer


def run_thread():
    """Run the websocket server in a new thread."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(start())
    loop.run_forever()


def run():
    """Non-async function that will start the websocket server
    on a dedicated thread. This thread is a daemon so it will
    close when the parent thread closes.
    """
    threading.Thread(target=run_thread, daemon=True).start()
    logging.info(_("Frontend popup websocket started."))
