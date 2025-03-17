import re
from typing import Dict, List, Optional, Union

class LdfParseError(Exception):
    """Exception raised for errors during LDF parsing."""
    pass

class LdfSignal:
    def __init__(self):
        self.name: str = ""
        self.size: int = 0
        self.init_value: int = 0
        self.publisher: str = ""
        self.subscribers: List[str] = []

class LdfFrame:
    def __init__(self):
        self.name: str = ""
        self.id: int = 0
        self.length: int = 0
        self.signals: Dict[str, LdfSignal] = {}
        self.publisher: str = ""

class LdfNode:
    def __init__(self):
        self.name: str = ""
        self.protocol_version: str = ""
        self.configured_nad: int = 0
        self.initial_nad: int = 0
        self.supplier_id: int = 0
        self.function_id: int = 0
        self.variant_id: int = 0

class LdfScheduleEntry:
    def __init__(self):
        self.frame: str = ""
        self.delay: float = 0.0

class LdfParser:
    def __init__(self):
        self.protocol_version: str = ""
        self.language_version: str = ""
        self.speed: int = 19200
        self.master: Optional[LdfNode] = None
        self.slaves: Dict[str, LdfNode] = {}
        self.signals: Dict[str, LdfSignal] = {}
        self.frames: Dict[str, LdfFrame] = {}
        self.schedule_tables: Dict[str, List[LdfScheduleEntry]] = {}

    def parse_file(self, file_path: str) -> None:
        """Parse an LDF file and populate the parser's data structures."""
        try:
            with open(file_path, 'r') as f:
                content = f.read()

            # Remove comments
            content = re.sub(r'/\*.*?\*/', '', content, flags=re.DOTALL)
            content = re.sub(r'//.*$', '', content, flags=re.MULTILINE)

            # Parse header section
            self._parse_header(content)
            
            # Parse nodes section
            self._parse_nodes(content)
            
            # Parse signals section
            self._parse_signals(content)
            
            # Parse frames section
            self._parse_frames(content)
            
            # Parse schedule tables
            self._parse_schedule_tables(content)

        except Exception as e:
            raise LdfParseError(f"Error parsing LDF file: {str(e)}")

    def _parse_header(self, content: str) -> None:
        """Parse the LDF header section."""
        # Parse LIN protocol version
        match = re.search(r'LIN_protocol_version\s*=\s*"([^"]+)"', content)
        if match:
            self.protocol_version = match.group(1)

        # Parse LIN language version
        match = re.search(r'LIN_language_version\s*=\s*"([^"]+)"', content)
        if match:
            self.language_version = match.group(1)

        # Parse LIN speed
        match = re.search(r'LIN_speed\s*=\s*(\d+)\s*kbps', content)
        if match:
            self.speed = int(match.group(1)) * 1000

    def _parse_nodes(self, content: str) -> None:
        """Parse the nodes section of the LDF file."""
        # Parse master node
        master_match = re.search(r'Master:\s*([^{]+)', content)
        if master_match:
            self.master = LdfNode()
            self.master.name = master_match.group(1).strip()

        # Parse slave nodes
        slaves_section = re.search(r'Slaves\s*{([^}]+)}', content)
        if slaves_section:
            slave_nodes = re.findall(r'\s*([^\s,;]+)\s*[,;]?', slaves_section.group(1))
            for slave in slave_nodes:
                self.slaves[slave] = LdfNode()
                self.slaves[slave].name = slave

    def _parse_signals(self, content: str) -> None:
        """Parse the signals section of the LDF file."""
        signals_section = re.search(r'Signals\s*{([^}]+)}', content)
        if not signals_section:
            return

        signal_entries = re.finditer(
            r'([^:\s]+)\s*:\s*(\d+)\s*,\s*{([^}]+)}\s*,\s*(\d+)\s*,\s*([^;]+);',
            signals_section.group(1)
        )

        for match in signal_entries:
            signal = LdfSignal()
            signal.name = match.group(1)
            signal.size = int(match.group(2))
            signal.init_value = int(match.group(4))
            
            # Parse publisher and subscribers
            nodes = match.group(3).split(',')
            signal.publisher = nodes[0].strip()
            signal.subscribers = [node.strip() for node in nodes[1:]]
            
            self.signals[signal.name] = signal

    def _parse_frames(self, content: str) -> None:
        """Parse the frames section of the LDF file."""
        frames_section = re.search(r'Frames\s*{([^}]+)}', content)
        if not frames_section:
            return

        frame_entries = re.finditer(
            r'([^:\s]+)\s*:\s*(\d+)\s*,\s*([^,]+)\s*,\s*(\d+)\s*{([^}]+)}',
            frames_section.group(1)
        )

        for match in frame_entries:
            frame = LdfFrame()
            frame.name = match.group(1)
            frame.id = int(match.group(2))
            frame.publisher = match.group(3).strip()
            frame.length = int(match.group(4))
            
            # Parse signals in frame
            signals_text = match.group(5)
            signal_entries = re.finditer(
                r'([^,\s]+)\s*,\s*(\d+)\s*;',
                signals_text
            )
            
            for signal_match in signal_entries:
                signal_name = signal_match.group(1)
                if signal_name in self.signals:
                    frame.signals[signal_name] = self.signals[signal_name]
            
            self.frames[frame.name] = frame

    def _parse_schedule_tables(self, content: str) -> None:
        """Parse the schedule tables section of the LDF file."""
        schedule_section = re.search(r'Schedule_tables\s*{([^}]+)}', content)
        if not schedule_section:
            return

        table_entries = re.finditer(
            r'([^{\s]+)\s*{([^}]+)}',
            schedule_section.group(1)
        )

        for match in table_entries:
            table_name = match.group(1)
            entries = []
            
            schedule_entries = re.finditer(
                r'([^\s]+)\s+delay\s+(\d+\.?\d*)\s*ms;',
                match.group(2)
            )
            
            for entry_match in schedule_entries:
                entry = LdfScheduleEntry()
                entry.frame = entry_match.group(1)
                entry.delay = float(entry_match.group(2))
                entries.append(entry)
            
            self.schedule_tables[table_name] = entries