"""Abstract base class for LIN bus interface"""

import abc
from typing import Optional, Tuple, List

class BusState:
    """LIN bus state enumeration"""
    OPERATION = "OPERATION"  # Bus operation state
    UNINIT = "UNINIT"       # Bus uninitialized state 
    ERROR = "ERROR"         # Bus error state

class LINBus(abc.ABC):
    """
    Abstract base class for LIN bus interface.
    All concrete LIN interface implementations should inherit from this class.
    """

    def __init__(self, channel: str, bitrate: int = 19200):
        """
        Initialize LIN bus interface
        
        Args:
            channel: Channel identifier
            bitrate: Bit rate, default 19200
        """
        self.channel = channel
        self.bitrate = bitrate
        self._state = BusState.ACTIVE

    @property
    def state(self) -> BusState:
        """Get current bus state"""
        return self._state

    @abc.abstractmethod
    def send(self, msg_id: int, data: bytes, timeout: Optional[float] = None) -> None:
        """
        Send LIN message
        
        Args:
            msg_id: LIN message ID
            data: Data to send
            timeout: Timeout in seconds
        """
        pass

    @abc.abstractmethod
    def recv(self, timeout: Optional[float] = None) -> Tuple[int, bytes]:
        """
        Receive LIN message
        
        Args:
            timeout: Timeout in seconds
            
        Returns:
            Tuple containing message ID and data
        """
        pass

    @abc.abstractmethod
    def shutdown(self) -> None:
        """Close bus interface"""
        pass

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.shutdown().shutdown()
