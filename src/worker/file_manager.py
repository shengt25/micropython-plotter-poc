from typing import List, Tuple, Union
from PySide6.QtCore import QObject
import binascii

class FileManager(QObject):
    """MicroPython file system operation helper class"""

    @staticmethod
    def generate_list_dir_code(path: str) -> str:
        """Generate MicroPython code to list directory"""
        # Escape special characters in path
        escaped_path = path.replace("'", "\\'")

        code = f"""
import os, sys
_emit = lambda msg: sys.stdout.write(msg + '\\n')
try:
    items = []
    for name in sorted(os.listdir('{escaped_path}')):
        full_path = '{escaped_path}/' + name if '{escaped_path}' != '/' else '/' + name
        try:
            stat = os.stat(full_path)
            is_dir = stat[0] & 0x4000
            items.append((name, 'DIR' if is_dir else 'FILE'))
        except:
            items.append((name, 'UNKNOWN'))
    for item in items:
        _emit(item[0] + '|' + item[1])
except Exception as e:
    _emit('ERROR:' + str(e))
"""
        return code.strip()

    @staticmethod
    def parse_list_dir_result(raw_output: str) -> Tuple[bool, List[Tuple[str, bool]]]:
        """
        Parse directory listing result

        Returns:
            (success, [(name, is_dir), ...])
        """
        lines = raw_output.strip().split('\n')
        items = []

        for line in lines:
            line = line.strip()
            if not line:
                continue

            if line.startswith('ERROR:'):
                return (False, [])

            if '|' in line:
                name, type_str = line.split('|', 1)
                is_dir = (type_str == 'DIR')
                items.append((name, is_dir))

        return (True, items)

    @staticmethod
    def generate_read_file_code(path: str) -> str:
        """Generate MicroPython code to read file"""
        escaped_path = path.replace("'", "\\'")

        code = f"""import sys, binascii
try:
    sys.stdout.write('<<<FILE_START>>>')
    # 1. Read using 'rb' to use binary
    with open('{escaped_path}', 'rb') as f:
        while True:
            # 2. Read by chunk, 256 bytes at a time
            chunk = f.read(256)
            if not chunk: 
                break
            # 3. Convert to Hex to prevent special characters
            # hexlify returns bytes，need to decode to str and write to stdout
            sys.stdout.write(binascii.hexlify(chunk).decode())

    sys.stdout.write('<<<FILE_END>>>')
except Exception as e:
    # When error
    sys.stdout.write('<<<ERROR>>>')
    sys.stdout.write(str(e))
"""
        return code.strip()

    @staticmethod
    def parse_read_file_result(raw_output: str) -> Tuple[bool, Union[bytes, str]]:
        """
        Parse file read result (supports Hex restoration)

        Returns:
            (success, content_bytes)
            Note: Success returns bytes data, not str
        """
        # 1. Check error marker (corresponding to '<<<ERROR>>>' in previous code)
        if '<<<ERROR>>>' in raw_output:
            # Optionally extract specific error message
            # error_msg = raw_output.split('<<<ERROR>>>')[1]
            return (False, b"Device Error")

        # Backward compatibility for old code (just in case)
        if 'ERROR:' in raw_output and '<<<FILE_START>>>' not in raw_output:
            return (False, b"Device Error")

        # 2. Find markers
        start_marker = '<<<FILE_START>>>'
        end_marker = '<<<FILE_END>>>'

        start_idx = raw_output.find(start_marker)
        end_idx = raw_output.find(end_marker)

        if start_idx == -1 or end_idx == -1:
            return (False, b"Markers not found")

        # 3. Extract Hex string
        # Extract content between markers and strip whitespace
        hex_content = raw_output[start_idx + len(start_marker):end_idx].strip()

        # 4. Core step: Hex -> Bytes restoration
        try:
            # Convert hex string (e.g., "616263") back to binary (e.g., b"abc")
            content_bytes = binascii.unhexlify(hex_content)
            return (True, content_bytes)
        except binascii.Error:
            # Incorrect Hex format (e.g. chars missing during transmission)
            return (False, b"Hex Decode Error")

    @staticmethod
    def generate_write_file_code(path: str, content: str) -> str:
        """Generate MicroPython code to write file (use Hex encoding for transmission)"""
        escaped_path = path.replace("'", "\\'")

        # Encode (content) as hex string for transmission
        content_bytes = content.encode('utf-8')
        hex_content = binascii.hexlify(content_bytes).decode('ascii')

        code = f"""import sys, binascii
try:
    # Restore from Hex
    content_bytes = binascii.unhexlify('{hex_content}')
    # Write in binary mode
    with open('{escaped_path}', 'wb') as f:
        f.write(content_bytes)
    sys.stdout.write('<<<SUCCESS>>>')
except Exception as e:
    sys.stdout.write('<<<ERROR>>>')
    sys.stdout.write(str(e))
"""
        return code.strip()

    @staticmethod
    def parse_write_file_result(raw_output: str) -> bool:
        """
        Parse file write result

        Returns:
            success
        """
        return '<<<SUCCESS>>>' in raw_output and '<<<ERROR>>>' not in raw_output

    @staticmethod
    def generate_delete_path_code(path: str) -> str:
        """Generate MicroPython code to delete file/folder"""
        escaped_path = path.replace("'", "\\'")

        code = f"""import sys, os
def _join(parent, name):
    return parent + '/' + name if parent != '/' else '/' + name

def _remove(target):
    if target in ('', '/'):
        raise ValueError('Cannot delete root')
    stat = os.stat(target)
    is_dir = stat[0] & 0x4000
    if is_dir:
        for entry in os.listdir(target):
            _remove(_join(target, entry))
        os.rmdir(target)
    else:
        os.remove(target)

try:
    _remove('{escaped_path}')
    sys.stdout.write('<<<SUCCESS>>>')
except Exception as e:
    sys.stdout.write('<<<ERROR>>>')
    sys.stdout.write(str(e))
"""
        return code.strip()

    @staticmethod
    def parse_delete_path_result(raw_output: str) -> bool:
        """Parse delete result"""
        return '<<<SUCCESS>>>' in raw_output and '<<<ERROR>>>' not in raw_output
