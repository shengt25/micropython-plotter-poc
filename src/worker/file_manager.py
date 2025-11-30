from typing import List, Tuple
from PySide6.QtCore import QObject


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

        code = f"""
import sys
try:
    with open('{escaped_path}', 'r') as f:
        content = f.read()
    sys.stdout.write('<<<FILE_START>>>' + '\\n')
    sys.stdout.write(content)
    if not content.endswith('\\n'):
        sys.stdout.write('\\n')
    sys.stdout.write('<<<FILE_END>>>' + '\\n')
except Exception as e:
    sys.stdout.write('ERROR:' + str(e) + '\\n')
"""
        return code.strip()

    @staticmethod
    def parse_read_file_result(raw_output: str) -> Tuple[bool, str]:
        """
        解析读取文件的结果

        Returns:
            (success, content)
        """
        if 'ERROR:' in raw_output:
            return (False, "")

        # 查找标记
        start_marker = '<<<FILE_START>>>'
        end_marker = '<<<FILE_END>>>'

        start_idx = raw_output.find(start_marker)
        end_idx = raw_output.find(end_marker)

        if start_idx == -1 or end_idx == -1:
            return (False, "")

        # 提取内容（去除标记）
        content = raw_output[start_idx + len(start_marker):end_idx]

        # 去除首尾的换行符（标记后的换行）
        if content.startswith('\n'):
            content = content[1:]
        if content.endswith('\n'):
            content = content[:-1]

        return (True, content)

    @staticmethod
    def generate_write_file_code(path: str, content: str) -> str:
        """生成写入文件的 MicroPython 代码"""
        escaped_path = path.replace("'", "\\'")
        # 转义内容中的特殊字符
        escaped_content = content.replace("\\", "\\\\").replace("'", "\\'")

        code = f"""
import sys
try:
    with open('{escaped_path}', 'w') as f:
        f.write('''{escaped_content}''')
    sys.stdout.write('SUCCESS' + '\\n')
except Exception as e:
    sys.stdout.write('ERROR:' + str(e) + '\\n')
"""
        return code.strip()

    @staticmethod
    def parse_write_file_result(raw_output: str) -> bool:
        """
        解析写入文件的结果

        Returns:
            success
        """
        return 'SUCCESS' in raw_output and 'ERROR:' not in raw_output
