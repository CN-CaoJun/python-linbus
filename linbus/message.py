"""
This module contains the implementation of :class:`Message`.
"""

from typing import Optional

from copy import deepcopy
from math import isinf, isnan


class Message:
    """
    Messages do not support "dynamic" attributes, meaning any others than the
    documented ones, since it uses :obj:`~object.__slots__`.
    """

    __slots__ = (
        "timestamp",
        "dlc",
        "data",
        "__weakref__",  # support weak references to messages
    )

    def __init__(  # pylint: disable=too-many-locals, too-many-arguments
        self,
        timestamp: float = 0.0,
        dlc: Optional[int] = None,
        data: bytearray = None,
    ):
        """
        To create a message object, simply provide any of the below attributes
        together with additional parameters as keyword arguments to the constructor.
        """
        self.timestamp = timestamp

        if data is None :#or is_remote_frame:
            self.data = bytearray()
        elif isinstance(data, bytearray):
            self.data = data
        else:
            try:
                self.data = bytearray(data)
            except TypeError as error:
                err = f"Couldn't create message from {data} ({type(data)})"
                raise TypeError(err) from error

        if dlc is None:
            self.dlc = len(self.data)
        else:
            self.dlc = dlc
