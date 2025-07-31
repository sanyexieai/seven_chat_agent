#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from database.database import get_db
from models.database_models import MCPServer, MCPTool

db = next(get_db())
try:
    print('MCPServer表记录数:', db.query(MCPServer).count())
    print('MCPTool表记录数:', db.query(MCPTool).count())
    
    servers = db.query(MCPServer).all()
    print('服务器列表:', [s.name for s in servers])
    
    if servers:
        for server in servers:
            print(f'服务器: {server.name}, 状态: {server.is_active}')
            tools = db.query(MCPTool).filter(MCPTool.server_id == server.id).all()
            print(f'  工具数量: {len(tools)}')
finally:
    db.close() 