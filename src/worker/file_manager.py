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
import os
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
        print(item[0] + '|' + item[1])
except Exception as e:
    print('ERROR:' + str(e))
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
