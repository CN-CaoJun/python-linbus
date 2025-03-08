"""
This module contains the base implementation of :class:`BusABC` as well
"""
import importlib
from typing import *
from .bus import BusABC
from .vector.exceptions import InterfaceNotImplementedError

# interface_name => (module, classname)
BACKENDS: Dict[str, Tuple[str, str]] = {
    "vector": ("lin.vector", "VectorLinBus"),
}

def _get_class_for_interface(interface: str) -> Type[BusABC]:
    """
    Returns the main bus class for the given interface.

    :raises:
        NotImplementedError if the interface is not known
    :raises InterfaceNotImplementedError:
         if there was a problem while importing the interface or the bus class within that
    """
    # Find the correct backend
    try:
        module_name, class_name = BACKENDS[interface]
    except KeyError:
        raise NotImplementedError(
            f"Lin interface '{interface}' not supported"
        ) from None

    # Import the correct interface module
    try:
        module = importlib.import_module(module_name)
    except Exception as e:
        raise InterfaceNotImplementedError(
            f"Cannot import module {module_name} for Lin interface '{interface}': {e}"
        ) from None

    # Get the correct class
    try:
        bus_class = getattr(module, class_name)
    except Exception as e:
        raise InterfaceNotImplementedError(
            f"Cannot import class {class_name} from module {module_name} for Lin interface "
            f"'{interface}': {e}"
        ) from None

    return cast(Type[BusABC], bus_class)


class LinBus(BusABC):  # pylint: disable=abstract-method
    """Bus wrapper with configuration loading.
    :param numberOfChannels:
        numberOfChannels identification

    :param interface:
        See :ref:`interface names` for a list of supported interfaces.
        Set to ``None`` to let it be resolved automatically from the default
        :ref:`configuration`.

    :param app_name:
        assgin app name to vector

    :param kwargs:
        ``interface`` specific keyword arguments.

    :raises ValueError:
        if the ``channel`` could not be determined
    """
    def __new__(  # type: ignore
        cls: Any,
        channel: Union[int, Sequence[int], str],
        interface: Optional[str] = None,
        app_name: str = None,
        **kwargs: Any,
    ) -> BusABC:
        
        # resolve the bus class to use for that interface
        cls = _get_class_for_interface(interface)

        # make sure the bus can handle this config format
        print(f"app_name: {app_name}, channel: {channel}, kwargs: {kwargs}")
        bus = cls(app_name = app_name,channel=channel,**kwargs)

        return cast(BusABC, bus)
    


