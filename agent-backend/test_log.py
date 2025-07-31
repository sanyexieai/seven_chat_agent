#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试日志功能
"""

from utils.log_helper import get_logger

def test_log():
    print("开始测试日志功能...")
    
    # 获取logger
    logger = get_logger("test_log")
    
    # 测试不同级别的日志
    logger.debug("这是一条调试信息")
    logger.info("这是一条信息")
    logger.warning("这是一条警告")
    logger.error("这是一条错误")
    logger.critical("这是一条严重错误")
    
    print("日志测试完成")

if __name__ == "__main__":
    test_log() 