"""
This module contains the implementation of :class:`Message`.
"""

from typing import Optional, Union
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
    Implements LIN 2.1 PDU specification with complete validation and checksum support.
    
    According to LIN 2.1 specification, a PDU consists of:
    - Protected Identifier (PID): 6-bit identifier + 2-bit parity
    - Data Field: 2, 4, or 8 bytes of data
    - Checksum: Enhanced or Classic checksum for error detection
    """
    __slots__ = (
        "Pid",          # Protected Identifier (6-bit ID + 2-bit parity)
        "CS",           # Checksum (Enhanced or Classic)
        "Drc",          # Direction (0=Subscribe/Receive, 1=Publish/Transmit)
        "DL",           # Data Length (2, 4, or 8 bytes according to LIN 2.1)
        "Sduptr",       # Service Data Unit pointer (actual data bytes)
        "_frame_id",    # Original 6-bit frame identifier
        "_checksum_type", # Checksum type: 'enhanced' or 'classic'
        "_parity_bits"  # Calculated parity bits for PID
    )

    # LIN 2.1 specification constants
    VALID_DATA_LENGTHS = [2, 4, 8]  # Valid data lengths per LIN 2.1
    MAX_FRAME_ID = 0x3F  # 6-bit frame ID maximum value
    
    def __init__(self, 
                 timestamp: float = 0.0,
                 Pid: int = 0,
                 CS: int = 0,
                 Drc: int = 0,
                 DL: int = 8,
                 Sduptr: Union[bytearray, list, bytes] = None,
                 frame_id: Optional[int] = None,
                 checksum_type: str = 'enhanced'):
        """
        Initialize a LIN 2.1 PDU.
        
        Args:
            timestamp (float): Time when PDU was sent/received
            Pid (int): Protected Identifier (if 0, will be calculated from frame_id)
            CS (int): Checksum value (if 0, will be calculated)
            Drc (int): Direction (0=Subscribe/Receive, 1=Publish/Transmit)
            DL (int): Data Length (must be 2, 4, or 8 bytes per LIN 2.1)
            Sduptr: Service Data Unit data bytes
            frame_id (int): 6-bit frame identifier (0-63)
            checksum_type (str): 'enhanced' or 'classic' checksum
        """
        super().__init__(timestamp)
        
        # Validate data length according to LIN 2.1
        if DL not in self.VALID_DATA_LENGTHS:
            raise ValueError(f"Invalid data length {DL}. LIN 2.1 supports only {self.VALID_DATA_LENGTHS} bytes")
        
        # Validate direction
        if Drc not in (0, 1):
            raise ValueError("Invalid Direction: 0=Subscribe/Receive, 1=Publish/Transmit")
        
        # Validate checksum type
        if checksum_type not in ('enhanced', 'classic'):
            raise ValueError("Checksum type must be 'enhanced' or 'classic'")
        
        self.DL = DL
        self.Drc = Drc
        self._checksum_type = checksum_type
        
        # Initialize data
        if Sduptr is None:
            self.Sduptr = bytearray(DL)  # Initialize with zeros
        elif isinstance(Sduptr, bytearray):
            self.Sduptr = Sduptr
        else:
            self.Sduptr = bytearray(Sduptr)
        
        # Ensure data length matches DL
        if len(self.Sduptr) != DL:
            if len(self.Sduptr) < DL:
                # Pad with zeros
                self.Sduptr.extend([0] * (DL - len(self.Sduptr)))
            else:
                # Truncate to DL
                self.Sduptr = self.Sduptr[:DL]
        
        # Handle frame ID and PID
        if frame_id is not None:
            if not (0 <= frame_id <= self.MAX_FRAME_ID):
                raise ValueError(f"Frame ID must be 0-{self.MAX_FRAME_ID} (6-bit)")
            self._frame_id = frame_id
            self.Pid = self._calculate_pid(frame_id)
        else:
            if Pid == 0:
                raise ValueError("Either Pid or frame_id must be provided")
            self.Pid = Pid
            self._frame_id = self._extract_frame_id(Pid)
        
        # Calculate parity bits
        self._parity_bits = self._calculate_parity_bits(self._frame_id)
        
        # Calculate or set checksum
        if CS == 0:
            self.CS = self._calculate_checksum()
        else:
            self.CS = CS
    
    def _calculate_pid(self, frame_id: int) -> int:
        """
        Calculate Protected Identifier from 6-bit frame ID.
        PID = ID[5:0] + P1 + P0
        P0 = ID0 ⊕ ID1 ⊕ ID2 ⊕ ID4
        P1 = ¬(ID1 ⊕ ID3 ⊕ ID4 ⊕ ID5)
        """
        # Extract individual bits
        id0 = (frame_id >> 0) & 1
        id1 = (frame_id >> 1) & 1
        id2 = (frame_id >> 2) & 1
        id3 = (frame_id >> 3) & 1
        id4 = (frame_id >> 4) & 1
        id5 = (frame_id >> 5) & 1
        
        # Calculate parity bits
        p0 = id0 ^ id1 ^ id2 ^ id4
        p1 = ~(id1 ^ id3 ^ id4 ^ id5) & 1
        
        # Construct PID
        pid = frame_id | (p0 << 6) | (p1 << 7)
        return pid
    
    def _extract_frame_id(self, pid: int) -> int:
        """Extract 6-bit frame ID from PID."""
        return pid & 0x3F
    
    def _calculate_parity_bits(self, frame_id: int) -> tuple:
        """Calculate and return parity bits as tuple (P0, P1)."""
        id0 = (frame_id >> 0) & 1
        id1 = (frame_id >> 1) & 1
        id2 = (frame_id >> 2) & 1
        id3 = (frame_id >> 3) & 1
        id4 = (frame_id >> 4) & 1
        id5 = (frame_id >> 5) & 1
        
        p0 = id0 ^ id1 ^ id2 ^ id4
        p1 = ~(id1 ^ id3 ^ id4 ^ id5) & 1
        
        return (p0, p1)
    
    def _calculate_checksum(self) -> int:
        """
        Calculate LIN checksum according to LIN 2.1 specification.
        Enhanced checksum includes PID in calculation.
        Classic checksum only includes data bytes.
        """
        if self._checksum_type == 'enhanced':
            # Enhanced checksum includes PID
            checksum = self.Pid
        else:
            # Classic checksum (LIN 1.x compatibility)
            checksum = 0
        
        # Add all data bytes
        for byte in self.Sduptr:
            checksum += byte
            # Handle carry
            if checksum > 255:
                checksum = (checksum & 0xFF) + 1
        
        # Invert checksum
        return (~checksum) & 0xFF
    
    def validate_pid(self) -> bool:
        """Validate that PID parity bits are correct."""
        expected_pid = self._calculate_pid(self._frame_id)
        return self.Pid == expected_pid
    
    def validate_checksum(self) -> bool:
        """Validate that checksum is correct for current data."""
        expected_checksum = self._calculate_checksum()
        return self.CS == expected_checksum
    
    def update_checksum(self):
        """Recalculate and update checksum based on current data."""
        self.CS = self._calculate_checksum()
    
    def get_frame_id(self) -> int:
        """Get the 6-bit frame identifier."""
        return self._frame_id
    
    def get_parity_bits(self) -> tuple:
        """Get parity bits as tuple (P0, P1)."""
        return self._parity_bits
    
    def is_enhanced_checksum(self) -> bool:
        """Check if using enhanced checksum."""
        return self._checksum_type == 'enhanced'
    
    def set_data(self, data: Union[bytearray, list, bytes]):
        """
        Set new data and update checksum.
        
        Args:
            data: New data bytes
        """
        if isinstance(data, bytearray):
            self.Sduptr = data
        else:
            self.Sduptr = bytearray(data)
        
        # Ensure data length matches DL
        if len(self.Sduptr) != self.DL:
            if len(self.Sduptr) < self.DL:
                self.Sduptr.extend([0] * (self.DL - len(self.Sduptr)))
            else:
                self.Sduptr = self.Sduptr[:self.DL]
        
        # Update checksum
        self.update_checksum()
    
    def __repr__(self) -> str:
        """String representation of LIN PDU."""
        return (f"LINPDU(frame_id=0x{self._frame_id:02X}, "
                f"pid=0x{self.Pid:02X}, "
                f"drc={self.Drc}, "
                f"dl={self.DL}, "
                f"data={list(self.Sduptr)}, "
                f"checksum=0x{self.CS:02X}, "
                f"type={self._checksum_type})")


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
