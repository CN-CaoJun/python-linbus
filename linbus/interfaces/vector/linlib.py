"""
Ctypes wrapper module for Vector Lin Interface on win32/win64 systems.
"""

# Import Standard Python Modules
# ==============================
import ctypes
import logging
import time
import os
import threading
import numpy as np
from types import ModuleType
from typing import *

# Function to wait for a single object in Windows API
WaitForSingleObject: Optional[Callable[[int, int], int]]
# Constant representing an infinite timeout
INFINITE: Optional[int]
try:
    # Try builtin Python 3 Windows API
    from _winapi import WaitForSingleObject, INFINITE  # type: ignore
    # Flag indicating that Windows events are available
    HAS_EVENTS = True
except ImportError:
    WaitForSingleObject, INFINITE = None, None
    HAS_EVENTS = False

# Import custom exceptions
from .exceptions import VectorInterfaceNotImplementedError, VectorError

# Import custom classes
from linbus import (
    Message,
    BusABC
)

# Define Module Logger
# ====================
# Logger for this module
LOG = logging.getLogger(__name__)

# Import Vector API modules
# =========================
from . import xldefine, xlclass

# Import safely Vector API module for Travis tests
# Vector API driver module
xldriver: Optional[ModuleType] = None
try:
    from . import xldriver
except Exception as exc:
    # Log a warning if the Vector API driver cannot be imported
    LOG.warning("Could not import vxlapi: %s", exc)


class VectorLinBus(BusABC):
    def __init__(
        self,
        channel: Union[int, Sequence[int], str],
        app_name: Optional[str] = "CANalyzer",
        **kwargs: Any,
    ) -> None:
        """
        Initialize a VectorLinBus instance.

        :param channel:
            The channel indexes to create this bus with.
            Can also be a single integer or a comma separated string.
        :param app_name:
            Name of application in *Vector Hardware Config*.
            If set to `None`, the channel should be a global channel index.
        """
        # Flag indicating if the bus is in testing mode
        self.__testing = kwargs.get("_testing", False)
        if os.name != "nt" and not self.__testing:
            # Raise an error if the operating system is not Windows and not in testing mode
            raise VectorInterfaceNotImplementedError(
                f"The Vector interface is only supported on Windows, "
                f'but you are running "{os.name}"'
            )

        if xldriver is None:
            # Raise an error if the Vector API driver is not loaded
            raise VectorInterfaceNotImplementedError("The Vector API has not been loaded")

        # Keep a reference to the Vector API driver
        self.xldriver = xldriver
        # Open the Vector API driver
        self.xldriver.xlOpenDriver()

        # Bitrate of the bus
        self.bitrate = kwargs.get("bitrate", 16200)

        # Index of the master channel
        self.master_channel_index = kwargs.get("master_channel", None)

        # Name of the application encoded in bytes
        self._app_name = app_name.encode() if app_name is not None else b""

        # List of channel indexes
        self.channels: Sequence[int]
        if isinstance(channel, int):
            self.channels = [channel]
        elif isinstance(channel, str):  # must be checked before generic Sequence
            # Assume comma separated string of channels
            self.channels = [int(ch.strip()) for ch in channel.split(",")]
        elif isinstance(channel, Sequence):
            self.channels = [int(ch) for ch in channel]
        else:
            # Raise an error if the channel parameter is of an invalid type
            raise TypeError(
                f"Invalid type for parameter 'channel': {type(channel).__name__}"
            )

        # Get channel configurations
        channel_configs = get_channel_configs()

        # Mask representing all channels
        self.mask = 0
        # Dictionary mapping channel indexes to channel masks
        self.channel_masks: Dict[int, int] = {}
        # Dictionary mapping global channel indexes to local channel indexes
        self.index_to_channel: Dict[int, int] = {}

        for i in self.channels:
            # Find the global channel index
            channel_index = self._find_global_channel_idx(
                channel=i,
                app_name=app_name,
                channel_configs=channel_configs,
            )
            # Log the found channel index
            LOG.debug("Channel index %d found", channel_index)

            # Calculate the channel mask
            channel_mask = 1 << channel_index
            if channel_mask != self.channel_masks.get(i):
                # Raise an error if the channel mask is inconsistent
                raise VectorError.from_generic("error,contact wall.e")

            # Store the channel mask
            self.channel_masks[i] = channel_mask
            # Map the global channel index to the local channel index
            self.index_to_channel[channel_index] = i
            # Update the overall channel mask
            self.mask |= channel_mask

        # Information about the channel configuration
        self.channel_info = "Application {}: {}, {},{},{}".format(
            app_name,
            "LIN number: " + str(len(self.channels)),
            "bitrate:" + str(self.bitrate),
            ", ".join(f"LIN {ch + 1}" for ch in self.channels),
            ", ".join(f"Device Interface {di + 1}" for di in self.index_to_channel)
        )

        # Permission mask for channel access
        permission_mask = xlclass.XLaccess()
        # Set mask to request channel init permission if needed
        permission_mask.value = self.mask

        # Interface version of the Vector API
        interface_version = xldefine.XL_InterfaceVersion.XL_INTERFACE_VERSION

        # Port handle for the Vector API
        self.port_handle = xlclass.XLportHandle(xldefine.XL_INVALID_PORTHANDLE)
        # Open the port using the Vector API
        self.xldriver.xlOpenPort(
            self.port_handle,
            self._app_name,
            self.mask,
            permission_mask,
            256,
            interface_version,
            xldefine.XL_BusTypes.XL_BUS_TYPE_LIN,
        )
        # Store the permission mask value
        self.permission_mask = permission_mask.value

        # Log the port handle and permission mask
        LOG.debug(
            "Open Port: PortHandle: %d, PermissionMask: 0x%X",
            self.port_handle.value,
            permission_mask.value,
        )

        if self.port_handle == xlclass.XLportHandle(xldefine.XL_INVALID_PORTHANDLE):
            # Raise an error if the port cannot be opened
            raise VectorError.from_generic("error,xlOpenPort fail")

        # Initialize channels as master or slave
        for ch in self.channels:
            if self.master_channel_index and ch == self.master_channel_index:
                self.init_master(self.channel_masks[ch])
            else:
                self.init_slave(self.channel_masks[ch])

        # Set up event handling if available
        if True:
            # Event handle for receiving notifications
            self.event_handle = xlclass.XLhandle()
            # Set up notification for the port
            self.xldriver.xlSetNotification(self.port_handle, self.event_handle, 1)
        else:
            # Log a message if pywin32 is not installed
            LOG.info("Install pywin32 to avoid polling")

        # Call the superclass constructor
        super().__init__(channel=channel, **kwargs)

    def init_master(self, channel_masks: int):
        """
        Initialize a channel as a master.

        :param channel_masks: Channel mask for the master channel.
        """
        # Set the bitrate for the master channel
        self._set_bitrate(channel_masks, self.bitrate, True)
        # Set the data length code for the master channel
        self._set_dlc(channel_masks, 8)
        # Activate the master channel
        self._active_channel(channel_masks)
        # Flush the receive queue for the master channel
        self._flush_receive_queue()

    def init_slave(self, channel_masks: int):
        """
        Initialize a channel as a slave.

        :param channel_masks: Channel mask for the slave channel.
        """
        # Set the bitrate for the slave channel
        self._set_bitrate(channel_masks, self.bitrate, False)
        # Set the data length code for the slave channel
        self._set_dlc(channel_masks, 8)
        # Activate the slave channel
        self._active_channel(channel_masks)
        # Flush the receive queue for the slave channel
        self._flush_receive_queue()

    def send(self, linID: int):
        """
        Send a LIN request.

        :param linID: LIN ID of the request.
        """
        if self.master_channel_index is None:
            # Raise an error if no master channel is configured
            raise ValueError("No Master Channel")

        for ch in self.channels:
            if self.master_channel_index and ch == self.master_channel_index:
                # Send the LIN request using the Vector API
                xldriver.xlLinSendRequest(self.port_handle, self.channel_masks[ch], linID, 0)
                isRight = True
                break

    def set_send_msg(self, channel: int, msg: Message, linID: int, is_checksum: bool):
        """
        Set the message to be sent on a specific channel.

        :param channel: Channel index.
        :param msg: Message to be sent.
        :param linID: LIN ID of the message.
        :param is_checksum: Flag indicating if enhanced checksum should be used.
        """
        isRight = False
        # Checksum type
        cs = xldefine.XL_LinSetSlave.XL_LIN_CALC_CHECKSUM
        if is_checksum:
            cs = xldefine.XL_LinSetSlave.XL_LIN_CALC_CHECKSUM_ENHANCED
        for ch in self.channels:
            if ch == channel:
                # Get the message data
                data = msg.data
                # Get the message data length code
                dlc = msg.dlc
                # Set the slave message using the Vector API
                self._setSlave(self.channel_masks[ch], linID, data, dlc, cs)
                isRight = True
                break
        if not isRight:
            # Raise an error if the channel is not found
            raise ValueError("")

    def _find_global_channel_idx(
        self,
        channel: int,
        app_name: Optional[str],
        channel_configs: List["VectorChannelConfig"],
    ) -> int:
        """
        Find the global channel index.

        :param channel: Local channel index.
        :param app_name: Name of the application.
        :param channel_configs: List of channel configurations.
        :return: Global channel index.
        """
        if app_name:
            # Get the hardware configuration for the application
            hw_type, hw_index, hw_channel = self.get_application_config(
                app_name, channel
            )
            # Get the global channel index using the Vector API
            idx = cast(
                int, self.xldriver.xlGetChannelIndex(hw_type, hw_index, hw_channel)
            )
            if idx < 0:
                # Raise an error if the hardware is unavailable
                raise ValueError(
                    xldefine.XL_Status.XL_ERR_HW_NOT_PRESENT,
                    xldefine.XL_Status.XL_ERR_HW_NOT_PRESENT.name,
                    "xlGetChannelIndex",
                )

            if channel_configs[idx].channel_bus_capabilities & xldefine.XL_BusCapabilities.XL_BUS_ACTIVE_CAP_LIN:
                if channel_configs[idx].hw_type == hw_type:
                    # Get the channel mask using the Vector API
                    self.channel_masks[channel] = self.xldriver.xlGetChannelMask(hw_type, hw_index, hw_channel)
            return idx

        # Raise an error if the channel is not found
        raise ValueError(
            f"Channel {channel} not found. The 'channel' parameter must be "
            f"a valid global channel index if neither 'app_name' nor 'serial' were given.",
            error_code=xldefine.XL_Status.XL_ERR_HW_NOT_PRESENT,
        )

    def _read_bus_params(self, channel: int) -> "VectorBusParams":
        """
        Read the bus parameters for a specific channel.

        :param channel: Channel index.
        :return: Bus parameters for the channel.
        """
        # Get the channel mask
        channel_mask = self.channel_masks[channel]

        # Get the list of channel configurations
        vcc_list = get_channel_configs()
        for vcc in vcc_list:
            if vcc.channel_mask == channel_mask:
                # Return the bus parameters if the channel is found
                return vcc.bus_params

        # Raise an error if the channel configuration is not found
        raise ValueError(
            f"Channel configuration for channel {channel} not found."
        )

    def _set_dlc(self, channel_masks: int, len: int) -> None:
        """
        Set the data length code for a channel.

        :param channel_masks: Channel mask.
        :param len: Data length code.
        """
        # Create a ctypes array for the data length code
        dlc = (ctypes.c_char * 60)(*(len for i in range(60)))
        # Set the data length code using the Vector API
        self.xldriver.xlLinSetDLC(self.port_handle, channel_masks, dlc)

    def _setSlave(self, channel_masks: int, linID: int, data: bytes, len: int, checksum: xldefine.XL_LinSetSlave) -> None:
        """
        Set the slave message.

        :param channel_masks: Channel mask.
        :param linID: LIN ID of the message.
        :param data: Message data.
        :param len: Data length.
        :param checksum: Checksum type.
        """
        # Create a ctypes array for the message data
        p = (ctypes.c_char * 8)()
        n = 0
        for i, v in enumerate(data):
            p[i] = v

        t = p
        # Set the slave message using the Vector API
        self.xldriver.xlLinSetSlave(self.port_handle, channel_masks, linID, t, len, checksum)

    def _active_channel(self, channel_masks: int):
        """
        Activate a channel.

        :param channel_masks: Channel mask.
        """
        # Activate the channel using the Vector API
        self.xldriver.xlActivateChannel(self.port_handle, channel_masks, xldefine.XL_BusTypes.XL_BUS_TYPE_LIN, xldefine.XL_AC_Flags.XL_ACTIVATE_RESET_CLOCK)

    def _flush_receive_queue(self):
        """
        Flush the receive queue.
        """
        # Flush the receive queue using the Vector API
        self.xldriver.xlFlushReceiveQueue(self.port_handle)

    def _set_bitrate(self, channel_masks: int, bitrate: int, isMaster: bool) -> None:
        """
        Set the bitrate for a channel.

        :param channel_masks: Channel mask.
        :param bitrate: Bitrate value.
        :param isMaster: Flag indicating if the channel is a master.
        """
        # Structure for LIN channel parameters
        xlStatPar = xlclass.s_xl_lin_stat_par()
        if isMaster:
            # Set the LIN mode to master
            xlStatPar.LINMode = xldefine.XL_LinSetChannelParams.XL_LIN_MASTER
        else:
            # Set the LIN mode to slave
            xlStatPar.LINMode = xldefine.XL_LinSetChannelParams.XL_LIN_SLAVE
        # Set the bitrate
        xlStatPar.baudrate = bitrate
        # Set the LIN version
        xlStatPar.LINVersion = xldefine.XL_LinSetChannelParams.XL_LIN_VERSION_2_0
        # Set the channel parameters using the Vector API
        self.xldriver.xlLinSetChannelParams(
            self.port_handle,
            channel_masks,
            xlStatPar,
        )
        # Log the bitrate setting
        LOG.info("xlLinSetChannelParams: baudr.=%u ", bitrate)

    def recv(self, timeout: Optional[float]):
        """
        Receive a message from the bus.

        :param timeout: Timeout value in seconds.
        """
        # Call the internal receive method
        self._recv_internal(timeout)

    def _recv_internal(
        self, timeout: Optional[float]
    ) -> Tuple[Optional[Message], bool]:
        """
        Internal method to receive a message from the bus.

        :param timeout: Timeout value in seconds.
        :return: Tuple containing the received message and a flag indicating if the message is filtered.
        """
        # Calculate the end time if a timeout is specified
        end_time = time.time() + timeout if timeout is not None else None

        while True:
            try:
                # Receive a LIN message
                msg = self._recv_lin()
            except VectorError as exception:
                if exception.error_code != xldefine.XL_Status.XL_ERR_QUEUE_IS_EMPTY:
                    # Raise the error if it is not an empty queue error
                    raise
            else:
                pass
                # if msg:
                #     return msg, self._is_filtered

            # Check if the timeout has expired
            if end_time is not None and time.time() > end_time:
                return None

            if HAS_EVENTS:
                # Wait for receive event to occur
                if end_time is None:
                    time_left_ms = INFINITE
                else:
                    time_left = end_time - time.time()
                    time_left_ms = max(0, int(time_left * 1000))
                # Wait for the event using the Windows API
                WaitForSingleObject(self.event_handle.value, time_left_ms)  # type: ignore
            else:
                # Wait a short time until we try again
                time.sleep(self.poll_interval)

    def _recv_lin(self) -> Optional[Message]:
        """
        Receive a LIN message.

        :return: Received LIN message or None if no message is received.
        """
        # Structure for a LIN event
        xl_event = xlclass.XLevent()
        # Number of events to receive
        event_count = ctypes.c_uint(1)
        # Receive an event using the Vector API
        self.xldriver.xlReceive(self.port_handle, event_count, xl_event)

        # Log the LIN tag and channel index
        LOG.debug('lin tag{} channel idx {}'.format(xl_event.tag, xl_event.chanIndex))

        if xl_event.tag != xldefine.XL_EventTags.XL_LIN_MSG:
            # Handle the LIN event if it is not a LIN message
            self.handle_lin_event(xl_event)
            return None

        # Message type string
        ts = "RX: "
        if xl_event.tagData.linMsgApi.linMsg.flags & xldefine.XL_MessageFlags.XL_LIN_MSGFLAG_TX:
            ts = "TX: "
        elif xl_event.tagData.linMsgApi.linMsg.flags & xldefine.XL_MessageFlags.XL_LIN_MSGFLAG_CRCERROR:
            ts = "CRCERROR"
        else:
            ts = "RX:"

        # Message ID
        msg_id = xl_event.tagData.linMsgApi.linMsg.id
        # Data length code
        dlc = xl_event.tagData.linMsgApi.linMsg.dlc
        # Timestamp
        timestamp = xl_event.timeStamp * 1e-9
        # Message data
        data = xl_event.tagData.linMsgApi.linMsg.data[:dlc]
        # Channel index
        # channel = self.index_to_channel.get(xl_event.chanIndex)

        # Print the received message information
        print(ts + ":" + str(hex(msg_id)) + "  data:" + str([hex(i) for i in data]))

        # Return a Message object
        return Message(
            timestamp=timestamp,
            # arbitration_id=msg_id & 0x1FFFFFFF,
            dlc=dlc,
            data=data
        )

    def handle_lin_event(self, event: xlclass.XLevent) -> None:
        """
        Handle a LIN event.

        :param event: LIN event to handle.
        """
        pass

    def _get_tx_channel_mask(self, msgs: Sequence[Message]) -> int:
        """
        Get the transmit channel mask.

        :param msgs: Sequence of messages.
        :return: Transmit channel mask.
        """
        if len(msgs) == 1:
            # Return the channel mask for the single message
            return self.channel_masks.get(msgs[0].channel, self.mask)  # type: ignore[arg-type]
        else:
            # Return the overall channel mask
            return self.mask

    @staticmethod
    def _build_xl_event(msg: Message) -> xlclass.XLevent:
        """
        Build an XL event from a Message object.

        :param msg: Message object.
        :return: XL event.
        """
        # Message ID
        msg_id = msg.arbitration_id
        if msg.is_extended_id:
            msg_id |= xldefine.XL_MessageFlagsExtended.XL_CAN_EXT_MSG_ID

        # Message flags
        flags = 0
        if msg.is_remote_frame:
            flags |= xldefine.XL_MessageFlags.XL_CAN_MSG_FLAG_REMOTE_FRAME

        # Create an XL event
        xl_event = xlclass.XLevent()
        xl_event.tag = xldefine.XL_EventTags.XL_TRANSMIT_MSG
        xl_event.tagData.msg.id = msg_id
        xl_event.tagData.msg.dlc = msg.dlc
        xl_event.tagData.msg.flags = flags
        xl_event.tagData.msg.data = tuple(msg.data)

        return xl_event

    def flush_tx_buffer(self) -> None:
        """
        Flush the transmit buffer.
        """
        # Flush the transmit queue using the Vector API
        self.xldriver.xlCanFlushTransmitQueue(self.port_handle, self.mask)

    def shutdown(self) -> None:
        """
        Shutdown the bus.
        """
        # Call the superclass shutdown method
        super().shutdown()
        # Deactivate the channels using the Vector API
        self.xldriver.xlDeactivateChannel(self.port_handle, self.mask)
        # Close the port using the Vector API
        self.xldriver.xlClosePort(self.port_handle)
        # Close the driver using the Vector API
        self.xldriver.xlCloseDriver()

    def reset(self) -> None:
        """
        Reset the bus.
        """
        # Deactivate the channels using the Vector API
        self.xldriver.xlDeactivateChannel(self.port_handle, self.mask)
        # Activate the channels using the Vector API
        self.xldriver.xlActivateChannel(
            self.port_handle, self.mask, xldefine.XL_BusTypes.XL_BUS_TYPE_CAN, 0
        )

    @staticmethod
    def popup_vector_hw_configuration(wait_for_finish: int = 0) -> None:
        """
        Open vector hardware configuration window.

        :param wait_for_finish:
            Time to wait for user input in milliseconds.
        """
        if xldriver is None:
            # Raise an error if the Vector API driver is not loaded
            raise VectorInterfaceNotImplementedError("The Vector API has not been loaded")

        # Open the hardware configuration window using the Vector API
        xldriver.xlPopupHwConfig(ctypes.c_char_p(), ctypes.c_uint(wait_for_finish))

    @staticmethod
    def get_application_config(
        app_name: str, app_channel: int
    ) -> Tuple[Union[int, xldefine.XL_HardwareType], int, int]:
        """
        Retrieve information for an application in Vector Hardware Configuration.

        :param app_name:
            The name of the application.
        :param app_channel:
            The channel of the application.
        :return:
            Returns a tuple of the hardware type, the hardware index and the
            hardware channel.

        :raises can.interfaces.vector.VectorInitializationError:
            If the application name does not exist in the Vector hardware configuration.
        """
        if xldriver is None:
            # Raise an error if the Vector API driver is not loaded
            raise VectorInterfaceNotImplementedError("The Vector API has not been loaded")

        # Hardware type
        hw_type = ctypes.c_uint()
        # Hardware index
        hw_index = ctypes.c_uint()
        # Hardware channel
        hw_channel = ctypes.c_uint()
        # Application channel
        _app_channel = ctypes.c_uint(app_channel)

        try:
            # Get the application configuration using the Vector API
            xldriver.xlGetApplConfig(
                app_name.encode(),
                _app_channel,
                hw_type,
                hw_index,
                hw_channel,
                xldefine.XL_BusTypes.XL_BUS_TYPE_LIN,
            )
        except VectorError as e:
            # Raise an error if the application configuration cannot be retrieved
            raise VectorInterfaceNotImplementedError(
                error_code=e.error_code,
                error_string=(
                    f"Vector HW Config: Channel '{app_channel}' of "
                    f"application '{app_name}' is not assigned to any interface"
                    f"||||| TO Open Vector Hardware Config -> Application -> Create/Modify'{app_name}'->assigned right interface lin"
                ),
                function="xlGetApplConfig",
            ) from None
        return _hw_type(hw_type.value), hw_index.value, hw_channel.value

    @staticmethod
    def set_application_config(
        app_name: str,
        app_channel: int,
        hw_type: Union[int, xldefine.XL_HardwareType],
        hw_index: int,
        hw_channel: int,
        **kwargs: Any,
    ) -> None:
        """
        Modify the application settings in Vector Hardware Configuration.

        This method can also be used with a channel config dictionary::

            import can
            from can.interfaces.vector import VectorBus

            configs = can.detect_available_configs(interfaces=['vector'])
            cfg = configs[0]
            VectorBus.set_application_config(app_name="MyApplication", app_channel=0, **cfg)

        :param app_name:
            The name of the application. Creates a new application if it does
            not exist yet.
        :param app_channel:
            The channel of the application.
        :param hw_type:
            The hardware type of the interface.
            E.g XL_HardwareType.XL_HWTYPE_VIRTUAL
        :param hw_index:
            The index of the interface if multiple interface with the same
            hardware type are present.
        :param hw_channel:
            The channel index of the interface.

        :raises can.interfaces.vector.VectorInitializationError:
            If the application name does not exist in the Vector hardware configuration.
        """
        if xldriver is None:
            # Raise an error if the Vector API driver is not loaded
            raise VectorInterfaceNotImplementedError("The Vector API has not been loaded")

        # Set the application configuration using the Vector API
        xldriver.xlSetApplConfig(
            app_name.encode(),
            app_channel,
            hw_type,
            hw_index,
            hw_channel,
            xldefine.XL_BusTypes.XL_BUS_TYPE_CAN,
        )

    def set_timer_rate(self, timer_rate_ms: int) -> None:
        """
        Set the cyclic event rate of the port.

        Once set, the port will generate a cyclic event with the tag XL_EventTags.XL_TIMER.
        This timer can be used to keep an application alive. See XL Driver Library Description
        for more information

        :param timer_rate_ms:
            The timer rate in ms. The minimal timer rate is 1ms, a value of 0 deactivates
            the timer events.
        """
        # Convert the timer rate to 10us units
        timer_rate_10us = timer_rate_ms * 100
        # Set the timer rate using the Vector API
        self.xldriver.xlSetTimerRate(self.port_handle, timer_rate_10us)


class VectorBusParams(NamedTuple):
    """
    Named tuple representing the bus parameters.
    """
    # Bus type
    bus_type: xldefine.XL_BusTypes


class VectorChannelConfig(NamedTuple):
    """
    NamedTuple which contains the channel properties from Vector XL API.
    """
    # Channel name
    name: str
    # Hardware type
    hw_type: Union[int, xldefine.XL_HardwareType]
    # Hardware index
    hw_index: int
    # Hardware channel
    hw_channel: int
    # Channel index
    channel_index: int
    # Channel mask
    channel_mask: int
    # Channel capabilities
    channel_capabilities: xldefine.XL_ChannelCapabilities
    # Channel bus capabilities
    channel_bus_capabilities: xldefine.XL_BusCapabilities
    # Flag indicating if the channel is on the bus
    is_on_bus: bool
    # Connected bus type
    connected_bus_type: xldefine.XL_BusTypes
    # Bus parameters
    bus_params: VectorBusParams
    # Serial number
    serial_number: int
    # Article number
    article_number: int
    # Transceiver name
    transceiver_name: str


def _get_xl_driver_config() -> xlclass.XLdriverConfig:
    """
    Get the Vector XL driver configuration.

    :return: XL driver configuration.
    """
    if xldriver is None:
        # Raise an error if the Vector API driver is not available
        raise VectorError(
            error_code=xldefine.XL_Status.XL_ERR_DLL_NOT_FOUND,
            error_string="xldriver is unavailable",
            function="_get_xl_driver_config",
        )
    # Create a driver configuration object
    driver_config = xlclass.XLdriverConfig()
    # Open the driver using the Vector API
    xldriver.xlOpenDriver()
    # Get the driver configuration using the Vector API
    xldriver.xlGetDriverConfig(driver_config)
    # Close the driver using the Vector API
    xldriver.xlCloseDriver()
    return driver_config


def _read_bus_params_from_c_struct(bus_params: xlclass.XLbusParams) -> VectorBusParams:
    """
    Read the bus parameters from a C structure.

    :param bus_params: C structure containing the bus parameters.
    :return: VectorBusParams object.
    """
    return VectorBusParams(
        # Bus type
        bus_type=xldefine.XL_BusTypes(bus_params.busType),
    )


def get_channel_configs() -> List[VectorChannelConfig]:
    """
    Read channel properties from Vector XL API.

    :return: List of channel configurations.
    """
    try:
        # Get the driver configuration
        driver_config = _get_xl_driver_config()
    except VectorError:
        return []

    # List to store channel configurations
    channel_list: List[VectorChannelConfig] = []
    for i in range(driver_config.channelCount):
        # Get the channel configuration from the driver configuration
        xlcc: xlclass.XLchannelConfig = driver_config.channel[i]
        # Create a VectorChannelConfig object
        vcc = VectorChannelConfig(
            name=xlcc.name.decode(),
            hw_type=_hw_type(xlcc.hwType),
            hw_index=xlcc.hwIndex,
            hw_channel=xlcc.hwChannel,
            channel_index=xlcc.channelIndex,
            channel_mask=xlcc.channelMask,
            channel_capabilities=xldefine.XL_ChannelCapabilities(
                xlcc.channelCapabilities
            ),
            channel_bus_capabilities=xldefine.XL_BusCapabilities(
                xlcc.channelBusCapabilities
            ),
            is_on_bus=bool(xlcc.isOnBus),
            bus_params=_read_bus_params_from_c_struct(xlcc.busParams),
            connected_bus_type=xldefine.XL_BusTypes(xlcc.connectedBusType),
            serial_number=xlcc.serialNumber,
            article_number=xlcc.articleNumber,
            transceiver_name=xlcc.transceiverName.decode(),
        )
        # Add the channel configuration to the list
        channel_list.append(vcc)
    return channel_list


def _hw_type(hw_type: int) -> Union[int, xldefine.XL_HardwareType]:
    """
    Convert the hardware type to an XL_HardwareType enum or return the original value.

    :param hw_type: Hardware type value.
    :return: XL_HardwareType enum or the original value.
    """
    try:
        return xldefine.XL_HardwareType(hw_type)
    except ValueError:
        # Log a warning if the hardware type is unknown
        LOG.warning(f'Unknown XL_HardwareType value "{hw_type}"')
        return hw_type