import ETS2LA.variables as variables
from ETS2LA.UI import SendPopup
from typing import Literal
import logging
import time
import os


class LogMessage:
    timestamp: float
    message: str

    def __init__(self, timestamp: float = 0, message: str = ""):
        self.timestamp = timestamp
        self.message = message


class Log:
    game: Literal["ets2", "ats"]
    messages: list[LogMessage]

    _start_time: float
    _filepath: str
    _last_modified: float = 0
    _last_position: int = 0  # Track file position for seek-based reading
    _last_file_size: int = 0  # Track file size to detect log reset

    def __init__(self, game: Literal["ets2", "ats"], filepath: str):
        self.game = game
        self._start_time = time.perf_counter()
        self._filepath = filepath
        self.messages = []
        self._last_position = 0
        self._last_file_size = 0

    def parse_creation_line(self, line: str):
        # Handle and parse ************ : log created on : Tuesday September 30 2025 @ 13:14:05
        if "log created on" in line.lower():
            try:
                timestamp_str = line.split("log created on : ")[1].strip()
                timestamp = time.mktime(
                    time.strptime(timestamp_str, "%A %B %d %Y @ %H:%M:%S")
                )
                logging.info(f"Log created for game {self.game} at {timestamp}")
                SendPopup(
                    f"Found {self.game.upper()}! Log created at {time.ctime(timestamp)}."
                )
                self._start_time = timestamp
                self.messages = []
            except Exception:
                logging.exception(
                    f"[LogReader] Failed to parse log creation time from line: {line.strip()}"
                )

    def update(self) -> list[LogMessage]:
        try:
            modified = os.path.getmtime(self._filepath)
            file_size = os.path.getsize(self._filepath)
        except Exception:
            return []

        if modified > self._last_modified:
            self._last_modified = modified
            new_messages: list[LogMessage] = []

            # Detect log file reset (file got smaller = new log started)
            log_was_reset = file_size < self._last_file_size or len(self.messages) == 0

            with open(self._filepath, "r", encoding="utf-8", errors="ignore") as f:
                if log_was_reset:
                    # Log was reset or first read - read from beginning
                    self._last_position = 0
                    self.messages = []
                    lines = f.readlines()

                    if lines:
                        self.parse_creation_line(lines[0])
                        lines = lines[1:]
                else:
                    # Seek to last known position and read only new data
                    f.seek(self._last_position)
                    new_data = f.read()
                    lines = new_data.splitlines(keepends=True)

                # Update position for next read
                self._last_position = f.tell()
                self._last_file_size = file_size

                latest_message = self.messages[-1].timestamp if self.messages else 0
                for line in lines:
                    try:
                        timestamp_str = line.split(" : ")[0].strip()  # HH:MM:SS.mmm
                        hours, minutes, seconds = timestamp_str.split(":")
                        seconds, milliseconds = seconds.split(".")
                        timestamp = (
                            self._start_time
                            + (float(hours) * 3600)
                            + (float(minutes) * 60)
                            + float(seconds)
                            + float(milliseconds) / 1000
                        )
                        if timestamp > latest_message:
                            message = line.split(" : ", 1)[1].strip()
                            new_messages.append(
                                LogMessage(timestamp=timestamp, message=message)
                            )
                            latest_message = timestamp  # Update for next iteration
                    except Exception as e:
                        logging.error(
                            f"Failed to parse log line: {line.strip()}, error: {e}"
                        )

            self.messages += new_messages
            return new_messages

        return []  # No new messages


ETS2 = Log("ets2", variables.ETS2_LOG_PATH)
ATS = Log("ats", variables.ATS_LOG_PATH)
