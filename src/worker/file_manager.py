from typing import List, Tuple, Union
from PySide6.QtCore import QObject
import binascii

class FileManager(QObject):
    """MicroPython 文件系统操作辅助类"""

    @staticmethod
    def generate_list_dir_code(path: str) -> str:
        """生成列出目录的 MicroPython 代码"""
        # 转义路径中的特殊字符
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
        解析列出目录的结果

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
        """生成读取文件的 MicroPython 代码"""
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
        解析读取文件的结果 (支持 Hex 还原)

        Returns:
            (success, content_bytes)
            注意：成功时返回的是 bytes 类型数据，不是 str
        """
        # 1. 检查错误标记 (对应上一段代码中的 '<<<ERROR>>>')
        if '<<<ERROR>>>' in raw_output:
            # 你可以选择提取具体的错误信息
            # error_msg = raw_output.split('<<<ERROR>>>')[1]
            return (False, b"Device Error")

        # 兼容旧代码的错误标记 (以防万一)
        if 'ERROR:' in raw_output and '<<<FILE_START>>>' not in raw_output:
            return (False, b"Device Error")

        # 2. 查找标记
        start_marker = '<<<FILE_START>>>'
        end_marker = '<<<FILE_END>>>'

        start_idx = raw_output.find(start_marker)
        end_idx = raw_output.find(end_marker)

        if start_idx == -1 or end_idx == -1:
            return (False, b"Markers not found")

        # 3. 提取 Hex 字符串
        # 提取中间的内容，并使用 strip() 去除可能存在的首尾换行符或空白
        hex_content = raw_output[start_idx + len(start_marker):end_idx].strip()

        # 4. 核心步骤：Hex -> Bytes 还原
        try:
            # 将十六进制字符串 (如 "616263") 转换回二进制 (如 b"abc")
            content_bytes = binascii.unhexlify(hex_content)
            return (True, content_bytes)
        except binascii.Error:
            # 如果 Hex 格式不对（比如传输丢失了字符），这里会报错
            return (False, b"Hex Decode Error")

    @staticmethod
    def generate_write_file_code(path: str, content: str) -> str:
        """生成写入文件的 MicroPython 代码（使用 Hex 编码传输）"""
        escaped_path = path.replace("'", "\\'")

        # 将内容编码为 hex 字符串进行传输
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
        解析写入文件的结果

        Returns:
            success
        """
        return '<<<SUCCESS>>>' in raw_output and '<<<ERROR>>>' not in raw_output
