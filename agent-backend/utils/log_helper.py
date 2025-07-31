# -*- coding: utf-8 -*-
import logging
import sys
from typing import Optional, Dict, Any
from pathlib import Path
import os
import logging
import sys
from typing import Optional, Dict, Any
from pathlib import Path
from logging.handlers import TimedRotatingFileHandler, RotatingFileHandler
import datetime

from config.env import LOG_LEVEL


class ColoredFormatter(logging.Formatter):
    """彩色日志格式化器"""
    
    # ANSI 颜色代码
    COLORS = {
        'DEBUG': '\033[36m',      # 青色
        'INFO': '\033[32m',       # 绿色
        'WARNING': '\033[33m',    # 黄色
        'ERROR': '\033[31m',      # 红色
        'CRITICAL': '\033[35m',   # 紫色
        'RESET': '\033[0m'        # 重置颜色
    }
    
    # 预定义的颜色映射
    COLOR_MAP = {
        'black': '\033[30m',
        'red': '\033[31m',
        'green': '\033[32m',
        'yellow': '\033[33m',
        'blue': '\033[34m',
        'magenta': '\033[35m',
        'cyan': '\033[36m',
        'white': '\033[37m',
        'bright_black': '\033[90m',
        'bright_red': '\033[91m',
        'bright_green': '\033[92m',
        'bright_yellow': '\033[93m',
        'bright_blue': '\033[94m',
        'bright_magenta': '\033[95m',
        'bright_cyan': '\033[96m',
        'bright_white': '\033[97m',
        'reset': '\033[0m'
    }
    
    def __init__(self, fmt=None, datefmt=None, style='%', custom_colors=None):
        super().__init__(fmt, datefmt, style)
        self.custom_colors = custom_colors or {}
    
    def set_custom_colors(self, custom_colors: dict):
        """
        设置自定义颜色
        
        Args:
            custom_colors: 自定义颜色字典，格式为 {'DEBUG': 'red', 'INFO': 'blue', ...}
        """
        self.custom_colors = custom_colors
    
    def get_color(self, level_name: str) -> str:
        """
        获取指定级别的颜色代码
        
        Args:
            level_name: 日志级别名称
        
        Returns:
            str: 颜色代码
        """
        # 优先使用自定义颜色
        if level_name in self.custom_colors:
            color_name = self.custom_colors[level_name]
            if color_name in self.COLOR_MAP:
                return self.COLOR_MAP[color_name]
            elif color_name.startswith('\033['):
                return color_name  # 直接使用ANSI代码
        
        # 使用默认颜色
        return self.COLORS.get(level_name, '')
    
    def format(self, record):
        # 获取原始格式化的消息
        formatted = super().format(record)
        
        # 为不同级别添加颜色
        level_name = record.levelname
        color_code = self.get_color(level_name)
        
        if color_code:
            # 在级别名称前后添加颜色代码
            colored_level = f"{color_code}{level_name}{self.COLORS['RESET']}"
            # 替换原始级别名称
            formatted = formatted.replace(level_name, colored_level)
            
            # 为整个消息内容添加颜色（除了时间戳和名称部分）
            # 找到消息内容的位置
            message_start = formatted.find(record.getMessage())
            if message_start != -1:
                # 分割消息：时间戳和名称部分保持原色，消息内容添加颜色
                before_message = formatted[:message_start]
                message_content = formatted[message_start:]
                
                # 为消息内容添加颜色
                colored_message = f"{color_code}{message_content}{self.COLORS['RESET']}"
                formatted = before_message + colored_message
        
        return formatted


class LogHelper:
    """日志记录单例类"""
    
    _instance: Optional['LogHelper'] = None
    _initialized: bool = False
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if not self._initialized:
            self._loggers: Dict[str, logging.Logger] = {}
            # 优先从环境变量读取日志级别
            level = logging._nameToLevel.get(LOG_LEVEL.upper(), logging.ERROR)
            self._default_level = level
            self._default_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            self._log_file: Optional[Path] = None
            self._use_colors = True
            self._initialized = True
    
    def setup(
        self,
        level: int = logging.NOTSET,
        format_str: str = None,
        log_file: str = None,
        console_output: bool = True,
        use_colors: bool = True
    ) -> 'LogHelper':
        """
        设置日志配置
        """
        if level == logging.NOTSET or level is None:
            level = self._default_level
        self._use_colors = use_colors
        if format_str:
            self._default_format = format_str
        if log_file:
            self._log_file = Path(log_file)
            self._log_file.parent.mkdir(parents=True, exist_ok=True)
        root_logger = logging.getLogger()
        root_logger.setLevel(level)
        for handler in root_logger.handlers[:]:
            root_logger.removeHandler(handler)
        if self._use_colors and console_output:
            formatter = ColoredFormatter(self._default_format)
        else:
            formatter = logging.Formatter(self._default_format)
        if console_output:
            console_handler = logging.StreamHandler(sys.stdout)
            console_handler.setLevel(level)
            console_handler.setFormatter(formatter)
            root_logger.addHandler(console_handler)
        if self._log_file:
            file_formatter = logging.Formatter(self._default_format)
            log_name = self._log_file.stem
            log_dir = self._log_file.parent
            date_str = datetime.datetime.now().strftime("%Y-%m-%d")
            file_path = log_dir / f"{log_name}_{date_str}.log"
            file_handler = RotatingFileHandler(file_path, maxBytes=10*1024*1024, backupCount=3, encoding='utf-8')
            file_handler.setLevel(level)
            file_handler.setFormatter(file_formatter)
            root_logger.addHandler(file_handler)
        return self

    def get_logger(self, name: str, level: int = logging.NOTSET) -> logging.Logger:
        """
        获取指定名称的日志记录器
        """
        if name not in self._loggers:
            logger = logging.getLogger(name)
            if level != logging.NOTSET:
                logger.setLevel(level)
            else:
                logger.setLevel(self._default_level if self._default_level is not None else logging.ERROR)
            
            # 添加控制台处理器
            console_handler = logging.StreamHandler(sys.stdout)
            console_handler.setLevel(level if level != logging.NOTSET else (self._default_level if self._default_level is not None else logging.ERROR))
            
            if self._use_colors:
                formatter = ColoredFormatter(self._default_format)
            else:
                formatter = logging.Formatter(self._default_format)
            console_handler.setFormatter(formatter)
            logger.addHandler(console_handler)
            
            # 添加文件处理器
            log_dir = Path("logs")
            log_dir.mkdir(parents=True, exist_ok=True)
            date_str = datetime.datetime.now().strftime("%Y-%m-%d")
            file_path = log_dir / f"{name}_{date_str}.log"
            file_formatter = logging.Formatter(self._default_format)
            file_handler = RotatingFileHandler(file_path, maxBytes=10*1024*1024, backupCount=3, encoding='utf-8')
            file_handler.setLevel(level if level != logging.NOTSET else (self._default_level if self._default_level is not None else logging.ERROR))
            file_handler.setFormatter(file_formatter)
            logger.addHandler(file_handler)
            
            self._loggers[name] = logger
        return self._loggers[name]
    
    def set_level(self, name: str, level: int) -> None:
        """
        设置指定日志记录器的级别
        
        Args:
            name: 日志记录器名称
            level: 日志级别
        """
        logger = self.get_logger(name)
        logger.setLevel(level)
    
    def set_level_all(self, level: int) -> None:
        """
        设置所有日志记录器的级别
        
        Args:
            level: 日志级别
        """
        if level == logging.NOTSET or level is None:
            level = self._default_level
        for logger in self._loggers.values():
            logger.setLevel(level)

    
    def add_file_handler(self, name: str, log_file: str, level: int = logging.NOTSET) -> None:
        """
        为指定日志记录器添加文件处理器
        
        Args:
            name: 日志记录器名称
            log_file: 日志文件路径
            level: 日志级别（可选）
        """
        logger = self.get_logger(name)
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        
        file_handler = logging.FileHandler(log_path, encoding='utf-8')
        if level == logging.NOTSET or level is None:
            file_handler.setLevel(level)
        else:
            file_handler.setLevel(self._default_level)
        
        formatter = logging.Formatter(self._default_format)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    
    def remove_file_handler(self, name: str, log_file: str) -> None:
        """
        移除指定日志记录器的文件处理器
        
        Args:
            name: 日志记录器名称
            log_file: 日志文件路径
        """
        logger = self.get_logger(name)
        log_path = Path(log_file)
        
        for handler in logger.handlers[:]:
            if isinstance(handler, logging.FileHandler) and handler.baseFilename == str(log_path.absolute()):
                logger.removeHandler(handler)
                break
    
    def clear_loggers(self) -> None:
        """清除所有日志记录器"""
        self._loggers.clear()
    
    def get_logger_names(self) -> list:
        """获取所有日志记录器名称"""
        return list(self._loggers.keys())
    
    def is_logger_exists(self, name: str) -> bool:
        """检查日志记录器是否存在"""
        return name in self._loggers
    
    def set_colors(self, use_colors: bool) -> None:
        """
        设置是否使用彩色输出
        
        Args:
            use_colors: 是否使用彩色输出
        """
        self._use_colors = use_colors
    
    def set_custom_colors(self, custom_colors: dict) -> None:
        """
        设置自定义颜色
        
        Args:
            custom_colors: 自定义颜色字典，格式为 {'DEBUG': 'red', 'INFO': 'blue', ...}
        
        支持的颜色名称:
        - 基础颜色: black, red, green, yellow, blue, magenta, cyan, white
        - 亮色: bright_black, bright_red, bright_green, bright_yellow, bright_blue, bright_magenta, bright_cyan, bright_white
        - 也可以直接使用ANSI代码，如 '\033[31m'
        """
        # 更新所有现有的日志记录器的格式化器
        for logger in self._loggers.values():
            for handler in logger.handlers:
                if isinstance(handler.formatter, ColoredFormatter):
                    handler.formatter.set_custom_colors(custom_colors)
        
        # 更新根日志记录器的格式化器
        root_logger = logging.getLogger()
        for handler in root_logger.handlers:
            if isinstance(handler.formatter, ColoredFormatter):
                handler.formatter.set_custom_colors(custom_colors)
    
    def get_available_colors(self) -> dict:
        """
        获取所有可用的颜色
        
        Returns:
            dict: 可用颜色字典
        """
        return ColoredFormatter.COLOR_MAP.copy()


# 全局单例实例
log_helper = LogHelper()


def get_logger(name: str = "default", level: int = logging.NOTSET) -> logging.Logger:
    """
    获取日志记录器的便捷函数
    
    Args:
        name: 日志记录器名称
        level: 日志级别（可选）
    
    Returns:
        logging.Logger: 日志记录器实例
    """
    return log_helper.get_logger(name, level)


def setup_logging(
    level: int = logging.NOTSET,
    format_str: str = None,
    log_file: str = None,
    console_output: bool = True,
    use_colors: bool = True
) -> LogHelper:
    """
    设置日志配置的便捷函数
    
    Args:
        level: 日志级别
        format_str: 日志格式
        log_file: 日志文件路径
        console_output: 是否输出到控制台
        use_colors: 是否使用彩色输出
    
    Returns:
        LogHelper: 日志助手实例
    """
    return log_helper.setup(level, format_str, log_file, console_output, use_colors)


def set_custom_colors(custom_colors: dict) -> None:
    """
    设置自定义颜色的便捷函数
    
    Args:
        custom_colors: 自定义颜色字典，格式为 {'DEBUG': 'red', 'INFO': 'blue', ...}
    
    支持的颜色名称:
    - 基础颜色: black, red, green, yellow, blue, magenta, cyan, white
    - 亮色: bright_black, bright_red, bright_green, bright_yellow, bright_blue, bright_magenta, bright_cyan, bright_white
    - 也可以直接使用ANSI代码，如 '\033[31m'
    """
    log_helper.set_custom_colors(custom_colors)


def get_available_colors() -> dict:
    """
    获取所有可用颜色的便捷函数
    
    Returns:
        dict: 可用颜色字典
    """
    return log_helper.get_available_colors()




if __name__ == "__main__":
    # 测试函数
    def test_log_helper():
        """测试日志助手功能"""
        # 设置日志配置
        setup_logging(
            level=logging.DEBUG,
            format_str='%(asctime)s [%(name)s] %(levelname)s - %(message)s',
            log_file='test.log',
            console_output=True,
            use_colors=True
        )
        
        # 获取不同的日志记录器
        logger1 = get_logger()
        logger2 = get_logger("TestModule2", level=logging.WARNING)
        
        # 测试默认彩色日志记录
        print("=== 测试默认彩色日志输出 ===")
        logger1.debug("这是一条调试信息 (默认青色)")
        logger1.info("这是一条信息 (默认绿色)")
        logger1.warning("这是一条警告 (默认黄色)")
        logger1.error("这是一条错误 (默认红色)")
        logger1.critical("这是一条严重错误 (默认紫色)")
        
        # 测试自定义颜色
        print("\n=== 测试自定义颜色 ===")
        custom_colors = {
            'DEBUG': 'bright_blue',
            'INFO': 'bright_green', 
            'WARNING': 'bright_yellow',
            'ERROR': 'bright_red',
            'CRITICAL': 'bright_magenta'
        }
        set_custom_colors(custom_colors)
        
        logger1.debug("这是一条调试信息 (自定义亮蓝色)")
        logger1.info("这是一条信息 (自定义亮绿色)")
        logger1.warning("这是一条警告 (自定义亮黄色)")
        logger1.error("这是一条错误 (自定义亮红色)")
        logger1.critical("这是一条严重错误 (自定义亮紫色)")
        
        # 测试部分自定义颜色
        print("\n=== 测试部分自定义颜色 ===")
        partial_colors = {
            'ERROR': 'bright_cyan',  # 只修改错误级别
            'INFO': '\033[93m'       # 使用ANSI代码
        }
        set_custom_colors(partial_colors)
        
        logger1.debug("调试信息 (保持默认青色)")
        logger1.info("信息 (使用ANSI代码黄色)")
        logger1.warning("警告 (保持默认黄色)")
        logger1.error("错误 (自定义亮青色)")
        logger1.critical("严重错误 (保持默认紫色)")
        
        # 显示可用颜色
        print("\n=== 可用颜色列表 ===")
        colors = get_available_colors()
        for color_name, color_code in colors.items():
            if color_name != 'reset':
                print(f"{color_code}{color_name}{colors['reset']}", end=" ")
        
        # 测试单例特性
        log_helper2 = LogHelper()
        print(f"\n\n单例测试: {log_helper is log_helper2}")
        
        # 显示所有日志记录器
        print(f"所有日志记录器: {log_helper.get_logger_names()}")
        
        # 测试关闭颜色
        print("\n=== 测试关闭颜色 ===")
        log_helper.set_colors(False)
        logger1.info("这条信息没有颜色")
        logger1.error("这条错误没有颜色")
        
        # 重新开启颜色
        log_helper.set_colors(True)
        logger1.info("这条信息重新有颜色了")

    test_log_helper()
