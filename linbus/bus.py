"""
Contains the ABC bus implementation and its documentation.
"""

from typing import *

from abc import ABC, ABCMeta, abstractmethod
import logging
import threading
from time import time

# from can.broadcastmanager import ThreadBasedCyclicSendTask, CyclicSendTaskABC
from .message import Message

# Create a logger for this module
LOG = logging.getLogger(__name__)

class BusABC(metaclass=ABCMeta):
    """The Lin Bus Abstract Base Class that serves as the basis
    for all concrete interfaces.
    """
    # a string describing the underlying bus and/or channel
    channel_info = "unknown"
    # Log level for received messages
    RECV_LOGGING_LEVEL = 9

    @abstractmethod
    def __init__(
        self,
        channel: Union[int, Sequence[int], str],
        **kwargs: object
    ):
        """
        Initialize the bus with a channel and optional keyword arguments.

        :param channel: The channel to use for the bus. Can be an integer, a sequence of integers, or a string.
        :param kwargs: Additional keyword arguments.
        """
        pass

    def __str__(self) -> str:
        """
        Return a string representation of the bus, which is the channel information.

        :return: A string representing the channel information.
        """
        return self.channel_info

    def recv(self, timeout: Optional[float] = None) -> Optional[Message]:
        """
        Block waiting for a message from the Bus.

        :param timeout: seconds to wait for a message or None to wait indefinitely
        :return: :obj:`None` on timeout
        """
        start = time()
        time_left = timeout

        while True:
            # try to get a message
            msg, already_filtered = self._recv_internal(timeout=time_left)

            # return it, if it matches
            if msg:
                LOG.log(self.RECV_LOGGING_LEVEL, "Received: %s", msg)
                return msg

            # if not, and timeout is None, try indefinitely
            elif timeout is None:
                continue

            # try next one only if there still is time, and with
            # reduced timeout
            else:
                time_left = timeout - (time() - start)

                if time_left > 0:
                    continue

                return None

    def _recv_internal(
        self, timeout: Optional[float]
    ) -> Tuple[Optional[Message], bool]:
        """
        Internal method to receive a message from the bus.

        :param timeout: seconds to wait for a message or None to wait indefinitely
        :return: A tuple containing the received message (or None) and a boolean indicating if the message was already filtered.
        """
        raise NotImplementedError("Trying to read from a write only bus?")

    @abstractmethod
    def send(self, linID: int):
        """
        Send a message to the bus.

        :param linID: The LIN ID of the message to send.
        """
        raise NotImplementedError("Trying to write to a readonly bus?")

    @abstractmethod
    def set_send_msg(self, channel: int, msg: Message, linID: int, is_checksum: bool):
        """
        Set a message to be sent on the bus.

        :param channel: The channel on which to send the message.
        :param msg: The message to send.
        :param linID: The LIN ID of the message.
        :param is_checksum: A boolean indicating if a checksum should be used.
        """
        raise NotImplementedError("Trying to write to a readonly bus?")

    def __iter__(self) -> Iterator[Message]:
        """
        Iterate over messages received from the bus.

        :return: An iterator that yields messages received from the bus.
        """
        while True:
            msg = self.recv(timeout=1.0)
            if msg is not None:
                yield msg

    def shutdown(self) -> None:
        """
        Shutdown the bus.

        This method stops all periodic tasks associated with the bus.
        """
        # self.stop_all_periodic_tasks()
        pass

    def __enter__(self):
        """
        Enter the context manager.

        :return: The bus object itself.
        """
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """
        Exit the context manager and shut down the bus.

        :param exc_type: The type of the exception raised, if any.
        :param exc_val: The value of the exception raised, if any.
        :param exc_tb: The traceback of the exception raised, if any.
        """
        self.shutdown()
