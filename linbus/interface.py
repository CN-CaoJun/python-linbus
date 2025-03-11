"""LIN Bus Interface Module

This module provides the core implementation for LIN (Local Interconnect Network) bus interfaces.
It includes the base implementation of BusABC class and a dynamic backend loading system
that allows different LIN hardware interfaces to be used interchangeably.
"""
import importlib
from typing import *
from .bus import BusABC
from .vector.exceptions import InterfaceNotImplementedError

# Dictionary mapping interface names to their corresponding module and class names
# Format: interface_name => (module_path, class_name)
BACKENDS: Dict[str, Tuple[str, str]] = {
    "vector": ("lin.vector", "VectorLinBus"),
}

def _get_class_for_interface(interface: str) -> Type[BusABC]:
    """Dynamically loads and returns the appropriate bus class for the specified interface.

    This function implements a plugin-like system for LIN interfaces by dynamically
    importing the required module and class based on the interface name.

    Args:
        interface: Name of the interface to load (must be a key in BACKENDS)

    Returns:
        The bus class for the specified interface

    Raises:
        NotImplementedError: If the requested interface is not registered in BACKENDS
        InterfaceNotImplementedError: If there are problems importing the interface module or class
    """
    # Look up the module and class names for the requested interface
    try:
        module_name, class_name = BACKENDS[interface]
    except KeyError:
        raise NotImplementedError(
            f"Lin interface '{interface}' not supported"
        ) from None

    # Dynamically import the interface module
    try:
        module = importlib.import_module(module_name)
    except Exception as e:
        raise InterfaceNotImplementedError(
            f"Cannot import module {module_name} for Lin interface '{interface}': {e}"
        ) from None

    # Get the interface class from the module
    try:
        bus_class = getattr(module, class_name)
    except Exception as e:
        raise InterfaceNotImplementedError(
            f"Cannot import class {class_name} from module {module_name} for Lin interface "
            f"'{interface}': {e}"
        ) from None

    return cast(Type[BusABC], bus_class)


class LinBus(BusABC):  # pylint: disable=abstract-method
    """Factory class for creating LIN bus interface instances.

    This class serves as a high-level factory that creates the appropriate bus interface
    instance based on the specified interface type. It provides a unified way to
    instantiate different LIN hardware interfaces while handling configuration and
    initialization.

    Args:
        channel: Channel identifier for the LIN interface. Can be an integer, sequence of integers,
                or a string depending on the interface type.
        interface: Name of the interface to use (must be registered in BACKENDS).
                  If None, will attempt to use a default configuration.
        app_name: Application name to identify this connection to the Vector interface.
        kwargs: Additional interface-specific configuration parameters.

    Returns:
        An instance of the appropriate BusABC subclass for the specified interface.

    Raises:
        ValueError: If the channel configuration is invalid
        NotImplementedError: If the specified interface is not supported
        InterfaceNotImplementedError: If there are problems initializing the interface
    """
    def __new__(  # type: ignore
        cls: Any,
        channel: Union[int, Sequence[int], str],
        interface: Optional[str] = None,
        app_name: str = None,
        **kwargs: Any,
    ) -> BusABC:
        
        # Dynamically load the appropriate interface class
        cls = _get_class_for_interface(interface)

        # Create and return an instance of the interface
        print(f"app_name: {app_name}, channel: {channel}, kwargs: {kwargs}")
        bus = cls(app_name = app_name,channel=channel,**kwargs)

        return cast(BusABC, bus)
    


