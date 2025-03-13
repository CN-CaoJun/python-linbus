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


class LINPDU(Message):
    """
    Implements AUTOSAR LIN PDU specification with enhanced validation
    """
    __slots__ = (
        "Pid",      # Protocol ID
        "CS",       # Checksum
        "Drc",      # Direction
        "DL",       # Data Length
        "Sduptr"    # Service Data Unit pointer
    )

    def __init__(self, 
                 timestamp: float = 0.0,
                 Pid: int = 0,
                 CS: int = 0,
                 Drc: int = 0,
                 DL: int = 0,
                 Sduptr: bytearray = None):
        
        super().__init__(timestamp)
        
        self.Pid = Pid
        self.CS = CS
        self.Drc = Drc
        self.DL = DL
        
        if Sduptr is None:
            self.Sduptr = bytearray()
        elif isinstance(Sduptr, bytearray):
            self.Sduptr = Sduptr
        else:
            self.Sduptr = bytearray(Sduptr)

        # LIN protocol validation
        if self.DL > 8:
            raise ValueError("LIN PDUs cannot exceed 8 data bytes")
        if self.Drc not in (0, 1):
            raise ValueError("Invalid LIN Direction (0=Receive, 1=Transmit)")


class LINFrame(Message):
    """
    Implementation of LIN frame based on OpenLIN data layer frame structure.
    Inherits from Message class and adds LIN-specific attributes.
    """
    __slots__ = (
        "pid",      # Protocol ID field
        "length",   # Length of data
        "checksum"  # LIN frame checksum
    )

    def __init__(self,
                 timestamp: float = 0.0,
                 pid: int = 0,
                 length: int = 0,
                 data: bytearray = None,
                 checksum: int = 0):
        """
        Initialize a LIN frame.

        Args:
            timestamp (float): Time when frame was sent/received
            pid (int): Protocol ID field identifying the frame
            length (int): Length of data in bytes
            data (bytearray): Pointer to frame data bytes
            checksum (int): Frame checksum for error detection
        """
        super().__init__(timestamp=timestamp, dlc=length, data=data)

        self.pid = pid
        self.length = length
        self.checksum = checksum

        # Validate frame length
        if self.length > 8:
            raise ValueError("LIN frame data cannot exceed 8 bytes")
