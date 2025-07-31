import React, { useState, useEffect } from 'react';
import './MCPPage.css';

interface MCPServer {
  id: number;
  name: string;
  display_name: string;
  description?: string;
  transport: string;
  command?: string;
  args?: string[];
  env?: Record<string, string>;
  url?: string;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

interface MCPTool {
  id: number;
  server_id: number;
  name: string;
  display_name?: string;
  description?: string;
  tool_type: string;
  input_schema?: any;
  output_schema?: any;
  examples?: any[];
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

interface MCPFormData {
  name: string;
  display_name: string;
  description: string;
  transport: string;
  command: string;
  args: string[];
  env: Record<string, string>;
  url: string;
}

const MCPPage: React.FC = () => {
  const [servers, setServers] = useState<MCPServer[]>([]);
  const [tools, setTools] = useState<MCPTool[]>([]);
  const [selectedServer, setSelectedServer] = useState<MCPServer | null>(null);
  const [showServerForm, setShowServerForm] = useState(false);
  const [showToolForm, setShowToolForm] = useState(false);
  const [editingServer, setEditingServer] = useState<MCPServer | null>(null);
  const [editingTool, setEditingTool] = useState<MCPTool | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string>('');
  const [success, setSuccess] = useState<string>('');
  const [showImportModal, setShowImportModal] = useState(false);
  const [importJson, setImportJson] = useState<string>('');

  const [serverForm, setServerForm] = useState<MCPFormData>({
    name: '',
    display_name: '',
    description: '',
    transport: 'stdio',
    command: '',
    args: [],
    env: {},
    url: ''
  });

  const [toolForm, setToolForm] = useState({
    name: '',
    display_name: '',
    description: '',
    tool_type: 'tool',
    input_schema: {},
    output_schema: {},
    examples: []
  });

  // 加载MCP服务器列表
  const loadServers = async () => {
    try {
      setLoading(true);
      const response = await fetch('/api/mcp/servers');
      if (response.ok) {
        const data = await response.json();
        setServers(data);
      } else {
        setError('加载MCP服务器失败');
      }
    } catch (err) {
      setError('加载MCP服务器失败');
    } finally {
      setLoading(false);
    }
  };

  // 加载工具列表
  const loadTools = async (serverId: number) => {
    try {
      const response = await fetch(`/api/mcp/servers/${serverId}/tools`);
      if (response.ok) {
        const data = await response.json();
        setTools(data);
      }
    } catch (err) {
      setError('加载工具失败');
    }
  };

  // 同步MCP工具
  const syncTools = async (serverName: string) => {
    try {
      setLoading(true);
      const response = await fetch(`/api/mcp/servers/${serverName}/sync`, {
        method: 'POST'
      });
      if (response.ok) {
        if (selectedServer) {
          await loadTools(selectedServer.id);
        }
        setSuccess('工具同步成功');
        setTimeout(() => setSuccess(''), 3000); // 3秒后自动清除
      } else {
        setError('同步工具失败');
      }
    } catch (err) {
      setError('同步工具失败');
    } finally {
      setLoading(false);
    }
  };

  // 创建MCP服务器
  const createServer = async () => {
    try {
      setLoading(true);
      const response = await fetch('/api/mcp/servers', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify(serverForm)
      });
      if (response.ok) {
        await loadServers();
        setShowServerForm(false);
        resetServerForm();
      } else {
        const error = await response.json();
        setError(error.detail || '创建服务器失败');
      }
    } catch (err) {
      setError('创建服务器失败');
    } finally {
      setLoading(false);
    }
  };

  // 更新MCP服务器
  const updateServer = async () => {
    if (!editingServer) return;
    try {
      setLoading(true);
      const response = await fetch(`/api/mcp/servers/${editingServer.id}`, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify(serverForm)
      });
      if (response.ok) {
        await loadServers();
        setShowServerForm(false);
        setEditingServer(null);
        resetServerForm();
      } else {
        const error = await response.json();
        setError(error.detail || '更新服务器失败');
      }
    } catch (err) {
      setError('更新服务器失败');
    } finally {
      setLoading(false);
    }
  };

  // 删除MCP服务器
  const deleteServer = async (serverId: number) => {
    if (!window.confirm('确定要删除这个MCP服务器吗？')) return;
    try {
      setLoading(true);
      const response = await fetch(`/api/mcp/servers/${serverId}`, {
        method: 'DELETE'
      });
      if (response.ok) {
        await loadServers();
        if (selectedServer?.id === serverId) {
          setSelectedServer(null);
          setTools([]);
        }
      } else {
        setError('删除服务器失败');
      }
    } catch (err) {
      setError('删除服务器失败');
    } finally {
      setLoading(false);
    }
  };

  // 创建MCP工具
  const createTool = async () => {
    if (!selectedServer) return;
    try {
      setLoading(true);
      const response = await fetch(`/api/mcp/servers/${selectedServer.id}/tools`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify(toolForm)
      });
      if (response.ok) {
        await loadTools(selectedServer.id);
        setShowToolForm(false);
        resetToolForm();
      } else {
        const error = await response.json();
        setError(error.detail || '创建工具失败');
      }
    } catch (err) {
      setError('创建工具失败');
    } finally {
      setLoading(false);
    }
  };

  // 删除MCP工具
  const deleteTool = async (toolId: number) => {
    if (!window.confirm('确定要删除这个工具吗？')) return;
    try {
      setLoading(true);
      const response = await fetch(`/api/mcp/tools/${toolId}`, {
        method: 'DELETE'
      });
      if (response.ok) {
        if (selectedServer) {
          await loadTools(selectedServer.id);
        }
      } else {
        setError('删除工具失败');
      }
    } catch (err) {
      setError('删除工具失败');
    } finally {
      setLoading(false);
    }
  };

  // 重置服务器表单
  const resetServerForm = () => {
    setServerForm({
      name: '',
      display_name: '',
      description: '',
      transport: 'stdio',
      command: '',
      args: [],
      env: {},
      url: ''
    });
  };

  // 重置工具表单
  const resetToolForm = () => {
    setToolForm({
      name: '',
      display_name: '',
      description: '',
      tool_type: 'tool',
      input_schema: {},
      output_schema: {},
      examples: []
    });
  };

  // 导入JSON配置
  const importFromJson = async () => {
    try {
      setLoading(true);
      const config = JSON.parse(importJson);
      
      if (!config.mcpServers || typeof config.mcpServers !== 'object') {
        setError('无效的MCP配置文件格式');
        return;
      }

      let importedCount = 0;
      for (const [name, serverConfig] of Object.entries(config.mcpServers)) {
        try {
          const response = await fetch('/api/mcp/servers', {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json'
            },
            body: JSON.stringify({
              name: name,
              display_name: `${name.charAt(0).toUpperCase() + name.slice(1)} MCP服务器`,
              description: `从JSON导入的${name} MCP服务器`,
              transport: (serverConfig as any).transport || 'stdio',
              command: (serverConfig as any).command || '',
              args: (serverConfig as any).args || [],
              env: (serverConfig as any).env || {},
              url: (serverConfig as any).url || ''
            })
          });
          
          if (response.ok) {
            importedCount++;
          }
        } catch (err) {
          console.error(`导入服务器 ${name} 失败:`, err);
        }
      }

      if (importedCount > 0) {
        await loadServers();
        setSuccess(`成功导入 ${importedCount} 个MCP服务器`);
        setTimeout(() => setSuccess(''), 3000);
        setShowImportModal(false);
        setImportJson('');
      } else {
        setError('没有成功导入任何服务器');
      }
    } catch (err) {
      setError('JSON格式错误，请检查配置文件');
    } finally {
      setLoading(false);
    }
  };

  // 处理文件上传
  const handleFileUpload = (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (file) {
      const reader = new FileReader();
      reader.onload = (e) => {
        const content = e.target?.result as string;
        setImportJson(content);
      };
      reader.readAsText(file);
    }
  };

  // 编辑服务器
  const editServer = (server: MCPServer) => {
    setEditingServer(server);
    setServerForm({
      name: server.name,
      display_name: server.display_name,
      description: server.description || '',
      transport: server.transport,
      command: server.command || '',
      args: server.args || [],
      env: server.env || {},
      url: server.url || ''
    });
    setShowServerForm(true);
  };

  // 选择服务器
  const selectServer = (server: MCPServer) => {
    setSelectedServer(server);
    loadTools(server.id);
  };

  useEffect(() => {
    loadServers();
  }, []);

  return (
    <div className="mcp-page">
      <div className="mcp-header">
        <h1>MCP配置管理</h1>
        <div className="header-actions">
          <button 
            className="btn btn-secondary"
            onClick={() => setShowImportModal(true)}
          >
            导入JSON
          </button>
          <button 
            className="btn btn-primary"
            onClick={() => {
              setShowServerForm(true);
              setEditingServer(null);
              resetServerForm();
            }}
          >
            添加MCP服务器
          </button>
        </div>
      </div>

      {error && (
        <div className="error-message">
          {error}
          <button onClick={() => setError('')}>×</button>
        </div>
      )}
      
      {success && (
        <div className="success-message">
          {success}
          <button onClick={() => setSuccess('')}>×</button>
        </div>
      )}

      <div className="mcp-content">
        {/* MCP服务器列表 */}
        <div className="servers-section">
          <h2>MCP服务器</h2>
          <div className="servers-list">
            {servers.map(server => (
              <div 
                key={server.id} 
                className={`server-item ${selectedServer?.id === server.id ? 'selected' : ''}`}
                onClick={() => selectServer(server)}
              >
                <div className="server-info">
                  <h3>{server.display_name}</h3>
                  <p>{server.description}</p>
                  <span className="transport">{server.transport}</span>
                </div>
                <div className="server-actions">
                  <button 
                    className="btn btn-small"
                    onClick={(e) => {
                      e.stopPropagation();
                      editServer(server);
                    }}
                  >
                    编辑
                  </button>
                  <button 
                    className="btn btn-small btn-danger"
                    onClick={(e) => {
                      e.stopPropagation();
                      deleteServer(server.id);
                    }}
                  >
                    删除
                  </button>
                  <button 
                    className="btn btn-small btn-secondary"
                    onClick={(e) => {
                      e.stopPropagation();
                      syncTools(server.name);
                    }}
                  >
                    同步工具
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* MCP工具列表 */}
        {selectedServer && (
          <div className="tools-section">
            <h2>{selectedServer.display_name} - 工具列表</h2>
            <button 
              className="btn btn-secondary"
              onClick={() => setShowToolForm(true)}
            >
              添加工具
            </button>
            <div className="tools-list">
              {tools.map(tool => (
                <div key={tool.id} className="tool-item">
                  <div className="tool-info">
                    <h4>{tool.display_name || tool.name}</h4>
                    <p>{tool.description}</p>
                    <span className="tool-type">{tool.tool_type}</span>
                  </div>
                  <div className="tool-actions">
                    <button 
                      className="btn btn-small btn-danger"
                      onClick={() => deleteTool(tool.id)}
                    >
                      删除
                    </button>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* MCP服务器表单 */}
      {showServerForm && (
        <div className="modal-overlay">
          <div className="modal">
            <div className="modal-header">
              <h3>{editingServer ? '编辑MCP服务器' : '添加MCP服务器'}</h3>
              <button onClick={() => setShowServerForm(false)}>×</button>
            </div>
            <div className="modal-body">
              <div className="form-group">
                <label>名称</label>
                <input
                  type="text"
                  value={serverForm.name}
                  onChange={(e) => setServerForm({...serverForm, name: e.target.value})}
                  placeholder="服务器名称"
                />
              </div>
              <div className="form-group">
                <label>显示名称</label>
                <input
                  type="text"
                  value={serverForm.display_name}
                  onChange={(e) => setServerForm({...serverForm, display_name: e.target.value})}
                  placeholder="显示名称"
                />
              </div>
              <div className="form-group">
                <label>描述</label>
                <textarea
                  value={serverForm.description}
                  onChange={(e) => setServerForm({...serverForm, description: e.target.value})}
                  placeholder="服务器描述"
                />
              </div>
              <div className="form-group">
                <label>传输协议</label>
                <select
                  value={serverForm.transport}
                  onChange={(e) => setServerForm({...serverForm, transport: e.target.value})}
                >
                  <option value="stdio">stdio</option>
                  <option value="sse">sse</option>
                  <option value="websocket">websocket</option>
                  <option value="streamable_http">streamable_http</option>
                </select>
              </div>
              <div className="form-group">
                <label>命令</label>
                <input
                  type="text"
                  value={serverForm.command}
                  onChange={(e) => setServerForm({...serverForm, command: e.target.value})}
                  placeholder="执行命令"
                />
              </div>
              <div className="form-group">
                <label>参数</label>
                <input
                  type="text"
                  value={serverForm.args.join(' ')}
                  onChange={(e) => setServerForm({...serverForm, args: e.target.value.split(' ')})}
                  placeholder="参数列表，用空格分隔"
                />
              </div>
              <div className="form-group">
                <label>URL</label>
                <input
                  type="text"
                  value={serverForm.url}
                  onChange={(e) => setServerForm({...serverForm, url: e.target.value})}
                  placeholder="服务器URL"
                />
              </div>
            </div>
            <div className="modal-footer">
              <button 
                className="btn btn-secondary"
                onClick={() => setShowServerForm(false)}
              >
                取消
              </button>
              <button 
                className="btn btn-primary"
                onClick={editingServer ? updateServer : createServer}
                disabled={loading}
              >
                {editingServer ? '更新' : '创建'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* MCP工具表单 */}
      {showToolForm && (
        <div className="modal-overlay">
          <div className="modal">
            <div className="modal-header">
              <h3>添加MCP工具</h3>
              <button onClick={() => setShowToolForm(false)}>×</button>
            </div>
            <div className="modal-body">
              <div className="form-group">
                <label>工具名称</label>
                <input
                  type="text"
                  value={toolForm.name}
                  onChange={(e) => setToolForm({...toolForm, name: e.target.value})}
                  placeholder="工具名称"
                />
              </div>
              <div className="form-group">
                <label>显示名称</label>
                <input
                  type="text"
                  value={toolForm.display_name}
                  onChange={(e) => setToolForm({...toolForm, display_name: e.target.value})}
                  placeholder="显示名称"
                />
              </div>
              <div className="form-group">
                <label>描述</label>
                <textarea
                  value={toolForm.description}
                  onChange={(e) => setToolForm({...toolForm, description: e.target.value})}
                  placeholder="工具描述"
                />
              </div>
              <div className="form-group">
                <label>工具类型</label>
                <select
                  value={toolForm.tool_type}
                  onChange={(e) => setToolForm({...toolForm, tool_type: e.target.value})}
                >
                  <option value="tool">tool</option>
                  <option value="resource">resource</option>
                  <option value="prompt">prompt</option>
                </select>
              </div>
            </div>
            <div className="modal-footer">
              <button 
                className="btn btn-secondary"
                onClick={() => setShowToolForm(false)}
              >
                取消
              </button>
              <button 
                className="btn btn-primary"
                onClick={createTool}
                disabled={loading}
              >
                创建
              </button>
            </div>
                     </div>
         </div>
       )}

       {/* 导入JSON模态框 */}
       {showImportModal && (
         <div className="modal-overlay">
           <div className="modal">
             <div className="modal-header">
               <h3>导入MCP配置</h3>
               <button onClick={() => setShowImportModal(false)}>×</button>
             </div>
             <div className="modal-body">
               <div className="form-group">
                 <label>选择JSON文件</label>
                 <input
                   type="file"
                   accept=".json"
                   onChange={handleFileUpload}
                   style={{ padding: '8px 0' }}
                 />
               </div>
               <div className="form-group">
                 <label>或直接粘贴JSON内容</label>
                 <textarea
                   value={importJson}
                   onChange={(e) => setImportJson(e.target.value)}
                   placeholder="粘贴MCP配置文件内容..."
                   rows={10}
                 />
               </div>
               <div className="import-example">
                 <h4>JSON格式示例：</h4>
                 <pre>{`{
  "mcpServers": {
    "ddg": {
      "command": "uvx",
      "args": ["duckduckgo-mcp-server"],
      "env": {}
    },
    "google": {
      "command": "python",
      "args": ["path/to/google_news_search.py", "--transport", "stdio"],
      "env": {
        "PYTHONPATH": "mcp_servers"
      }
    }
  }
}`}</pre>
               </div>
             </div>
             <div className="modal-footer">
               <button 
                 className="btn btn-secondary"
                 onClick={() => {
                   setShowImportModal(false);
                   setImportJson('');
                 }}
               >
                 取消
               </button>
               <button 
                 className="btn btn-primary"
                 onClick={importFromJson}
                 disabled={loading || !importJson.trim()}
               >
                 导入
               </button>
             </div>
           </div>
         </div>
       )}
     </div>
   );
 };

export default MCPPage; 