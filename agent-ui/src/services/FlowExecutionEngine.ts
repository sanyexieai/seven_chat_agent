import { FlowExecutionState, FlowExecutionStatus } from '../components/FlowExecutionTracker';

export interface FlowNode {
  id: string;
  type: string;
  position: { x: number; y: number };
  data: {
    label: string;
    nodeType: string;
    config: any;
    isStartNode?: boolean;
  };
}

export interface FlowEdge {
  id: string;
  source: string;
  target: string;
  type: string;
}

export interface FlowConfig {
  nodes: FlowNode[];
  edges: FlowEdge[];
  metadata: {
    name: string;
    description: string;
    version: string;
  };
}

export interface ExecutionContext {
  variables: Map<string, any>;
  currentNodeId: string | null;
  executionPath: string[];
  results: Map<string, any>;
  errors: Map<string, string>;
}

export interface NodeExecutionResult {
  success: boolean;
  result?: any;
  error?: string;
  duration: number;
  output?: any;
}

export class FlowExecutionEngine {
  private flowConfig: FlowConfig;
  private executionState: FlowExecutionState;
  private executionContext: ExecutionContext;
  private isRunning: boolean = false;
  private isPaused: boolean = false;
  private executionQueue: string[] = [];
  private nodeExecutors: Map<string, (node: FlowNode, context: ExecutionContext) => Promise<NodeExecutionResult>>;

  constructor(flowConfig: FlowConfig) {
    this.flowConfig = flowConfig;
    this.executionContext = {
      variables: new Map(),
      currentNodeId: null,
      executionPath: [],
      results: new Map(),
      errors: new Map()
    };
    
    this.executionState = {
      isRunning: false,
      isPaused: false,
      currentNodeId: null,
      completedNodes: [],
      failedNodes: [],
      skippedNodes: [],
      totalNodes: flowConfig.nodes.length,
      startTime: null,
      endTime: null,
      executionLog: [],
      nodeStatuses: this.initializeNodeStatuses()
    };

    this.nodeExecutors = new Map();
    this.initializeNodeExecutors();
  }

  private initializeNodeStatuses(): FlowExecutionStatus[] {
    return this.flowConfig.nodes.map(node => ({
      nodeId: node.id,
      status: 'pending',
      label: node.data.label,
      nodeType: node.data.nodeType,
      progress: 0
    }));
  }

  private initializeNodeExecutors(): void {
    // 注册各种节点类型的执行器
    this.nodeExecutors.set('llm', this.executeLLMNode.bind(this));
    this.nodeExecutors.set('agent', this.executeAgentNode.bind(this));
    this.nodeExecutors.set('tool', this.executeToolNode.bind(this));
    this.nodeExecutors.set('condition', this.executeConditionNode.bind(this));
    this.nodeExecutors.set('action', this.executeActionNode.bind(this));
    this.nodeExecutors.set('input', this.executeInputNode.bind(this));
    this.nodeExecutors.set('output', this.executeOutputNode.bind(this));
  }

  // 获取执行状态
  public getExecutionState(): FlowExecutionState {
    return { ...this.executionState };
  }

  // 开始执行流程
  public async startExecution(): Promise<void> {
    if (this.isRunning) {
      throw new Error('流程已在运行中');
    }

    this.isRunning = true;
    this.isPaused = false;
    this.executionState.isRunning = true;
    this.executionState.startTime = Date.now();
    this.executionState.currentNodeId = null;
    this.executionState.completedNodes = [];
    this.executionState.failedNodes = [];
    this.executionState.skippedNodes = [];
    this.executionState.executionLog = [];

    // 重置节点状态
    this.executionState.nodeStatuses = this.initializeNodeStatuses();

    // 重置执行上下文
    this.executionContext = {
      variables: new Map(),
      currentNodeId: null,
      executionPath: [],
      results: new Map(),
      errors: new Map()
    };

    this.addExecutionLog('system', 'start', '开始执行流程图', 'info');

    try {
      // 找到开始节点
      const startNodes = this.findStartNodes();
      if (startNodes.length === 0) {
        throw new Error('未找到开始节点');
      }

      // 将开始节点加入执行队列
      this.executionQueue = [...startNodes.map(n => n.id)];

      // 开始执行
      await this.executeNextNode();
    } catch (error) {
      this.handleExecutionError(error as Error);
    }
  }

  // 暂停执行
  public pauseExecution(): void {
    if (!this.isRunning) return;
    
    this.isPaused = true;
    this.executionState.isPaused = true;
    this.addExecutionLog('system', 'pause', '流程执行已暂停', 'warning');
  }

  // 恢复执行
  public resumeExecution(): void {
    if (!this.isRunning || !this.isPaused) return;
    
    this.isPaused = false;
    this.executionState.isPaused = false;
    this.addExecutionLog('system', 'resume', '流程执行已恢复', 'info');
    
    // 继续执行
    this.executeNextNode();
  }

  // 停止执行
  public stopExecution(): void {
    this.isRunning = false;
    this.isPaused = false;
    this.executionState.isRunning = false;
    this.executionState.isPaused = false;
    this.executionState.currentNodeId = null;
    this.executionQueue = [];
    this.addExecutionLog('system', 'stop', '流程执行已停止', 'warning');
  }

  // 重置执行状态
  public resetExecution(): void {
    this.stopExecution();
    this.executionState = {
      ...this.executionState,
      isRunning: false,
      isPaused: false,
      currentNodeId: null,
      completedNodes: [],
      failedNodes: [],
      skippedNodes: [],
      startTime: null,
      endTime: null,
      executionLog: [],
      nodeStatuses: this.initializeNodeStatuses()
    };
    this.executionContext = {
      variables: new Map(),
      currentNodeId: null,
      executionPath: [],
      results: new Map(),
      errors: new Map()
    };
  }

  // 查找开始节点（入度为0的节点）
  private findStartNodes(): FlowNode[] {
    const nodeIds = new Set(this.flowConfig.nodes.map(n => n.id));
    const targetIds = new Set(this.flowConfig.edges.map(e => e.target));
    
    return this.flowConfig.nodes.filter(node => !targetIds.has(node.id));
  }

  // 执行下一个节点
  private async executeNextNode(): Promise<void> {
    if (!this.isRunning || this.isPaused) return;

    if (this.executionQueue.length === 0) {
      // 所有节点执行完成
      this.completeExecution();
      return;
    }

    const nodeId = this.executionQueue.shift()!;
    const node = this.flowConfig.nodes.find(n => n.id === nodeId);
    
    if (!node) {
      this.addExecutionLog('system', 'error', `节点 ${nodeId} 不存在`, 'error');
      await this.executeNextNode();
      return;
    }

    // 更新当前执行节点
    this.executionState.currentNodeId = nodeId;
    this.executionContext.currentNodeId = nodeId;
    this.executionContext.executionPath.push(nodeId);

    try {
      // 更新节点状态为运行中
      this.updateNodeStatus(nodeId, 'running');
      this.addExecutionLog(nodeId, 'start', `开始执行节点: ${node.data.label}`);

      // 执行节点
      const executor = this.nodeExecutors.get(node.data.nodeType);
      if (!executor) {
        throw new Error(`未知的节点类型: ${node.data.nodeType}`);
      }

      const startTime = Date.now();
      const result = await executor(node, this.executionContext);
      const duration = Date.now() - startTime;

      if (result.success) {
        // 执行成功
        this.executionState.completedNodes.push(nodeId);
        this.executionContext.results.set(nodeId, result.result);
        this.updateNodeStatus(nodeId, 'completed', 100, result.result);
        this.addExecutionLog(nodeId, 'complete', `节点执行完成: ${node.data.label}`, 'success');

        // 将后续节点加入执行队列
        const nextNodes = this.findNextNodes(nodeId);
        this.executionQueue.push(...nextNodes);
      } else {
        // 执行失败
        this.executionState.failedNodes.push(nodeId);
        this.executionContext.errors.set(nodeId, result.error || '未知错误');
        this.updateNodeStatus(nodeId, 'failed', 100, undefined, result.error);
        this.addExecutionLog(nodeId, 'error', `节点执行失败: ${node.data.label}`, 'error');
      }

    } catch (error) {
      this.handleNodeExecutionError(nodeId, error as Error);
    }

    // 继续执行下一个节点
    await this.executeNextNode();
  }

  // 查找后续节点
  private findNextNodes(nodeId: string): string[] {
    return this.flowConfig.edges
      .filter(edge => edge.source === nodeId)
      .map(edge => edge.target);
  }

  // 更新节点状态
  private updateNodeStatus(
    nodeId: string, 
    status: FlowExecutionStatus['status'], 
    progress?: number,
    result?: any,
    error?: string
  ): void {
    const nodeStatus = this.executionState.nodeStatuses.find(n => n.nodeId === nodeId);
    if (nodeStatus) {
      nodeStatus.status = status;
      if (progress !== undefined) nodeStatus.progress = progress;
      if (result) nodeStatus.result = result;
      if (error) nodeStatus.error = error;
      
      if (status === 'running') {
        nodeStatus.startTime = Date.now();
      } else if (status === 'completed' || status === 'failed') {
        nodeStatus.endTime = Date.now();
        nodeStatus.duration = (nodeStatus.endTime - (nodeStatus.startTime || 0));
      }
    }
  }

  // 添加执行日志
  private addExecutionLog(
    nodeId: string, 
    action: string, 
    message: string, 
    level: 'info' | 'warning' | 'error' | 'success' = 'info'
  ): void {
    this.executionState.executionLog.push({
      timestamp: Date.now(),
      nodeId,
      action,
      message,
      level
    });
  }

  // 处理节点执行错误
  private handleNodeExecutionError(nodeId: string, error: Error): void {
    this.executionState.failedNodes.push(nodeId);
    this.executionContext.errors.set(nodeId, error.message);
    this.updateNodeStatus(nodeId, 'failed', 100, undefined, error.message);
    this.addExecutionLog(nodeId, 'error', `节点执行异常: ${error.message}`, 'error');
  }

  // 处理执行错误
  private handleExecutionError(error: Error): void {
    this.addExecutionLog('system', 'error', `流程执行失败: ${error.message}`, 'error');
    this.completeExecution();
  }

  // 完成执行
  private completeExecution(): void {
    this.isRunning = false;
    this.executionState.isRunning = false;
    this.executionState.endTime = Date.now();
    this.executionState.currentNodeId = null;
    
    const hasErrors = this.executionState.failedNodes.length > 0;
    this.addExecutionLog('system', 'complete', 
      hasErrors ? '流程执行完成（存在错误）' : '流程执行完成', 
      hasErrors ? 'warning' : 'success'
    );
  }

  // 节点执行器实现
  private async executeLLMNode(node: FlowNode, context: ExecutionContext): Promise<NodeExecutionResult> {
    const startTime = Date.now();
    
    try {
      // 模拟LLM节点执行
      await this.simulateNodeExecution(node, context);
      
      const result = {
        success: true,
        result: `LLM节点 ${node.data.label} 执行成功`,
        duration: Date.now() - startTime,
        output: `LLM输出: ${node.data.label}`
      };

      return result;
    } catch (error) {
      return {
        success: false,
        error: error instanceof Error ? error.message : '未知错误',
        duration: Date.now() - startTime
      };
    }
  }

  private async executeAgentNode(node: FlowNode, context: ExecutionContext): Promise<NodeExecutionResult> {
    const startTime = Date.now();
    
    try {
      await this.simulateNodeExecution(node, context);
      
      const result = {
        success: true,
        result: `智能体节点 ${node.data.label} 执行成功`,
        duration: Date.now() - startTime,
        output: `智能体输出: ${node.data.label}`
      };

      return result;
    } catch (error) {
      return {
        success: false,
        error: error instanceof Error ? error.message : '未知错误',
        duration: Date.now() - startTime
      };
    }
  }

  private async executeToolNode(node: FlowNode, context: ExecutionContext): Promise<NodeExecutionResult> {
    const startTime = Date.now();
    
    try {
      await this.simulateNodeExecution(node, context);
      
      const result = {
        success: true,
        result: `工具节点 ${node.data.label} 执行成功`,
        duration: Date.now() - startTime,
        output: `工具输出: ${node.data.label}`
      };

      return result;
    } catch (error) {
      return {
        success: false,
        error: error instanceof Error ? error.message : '未知错误',
        duration: Date.now() - startTime
      };
    }
  }

  private async executeConditionNode(node: FlowNode, context: ExecutionContext): Promise<NodeExecutionResult> {
    const startTime = Date.now();
    
    try {
      await this.simulateNodeExecution(node, context);
      
      const result = {
        success: true,
        result: `条件节点 ${node.data.label} 执行成功`,
        duration: Date.now() - startTime,
        output: `条件结果: true`
      };

      return result;
    } catch (error) {
      return {
        success: false,
        error: error instanceof Error ? error.message : '未知错误',
        duration: Date.now() - startTime
      };
    }
  }

  private async executeActionNode(node: FlowNode, context: ExecutionContext): Promise<NodeExecutionResult> {
    const startTime = Date.now();
    
    try {
      await this.simulateNodeExecution(node, context);
      
      const result = {
        success: true,
        result: `动作节点 ${node.data.label} 执行成功`,
        duration: Date.now() - startTime,
        output: `动作执行: ${node.data.label}`
      };

      return result;
    } catch (error) {
      return {
        success: false,
        error: error instanceof Error ? error.message : '未知错误',
        duration: Date.now() - startTime
      };
    }
  }

  private async executeInputNode(node: FlowNode, context: ExecutionContext): Promise<NodeExecutionResult> {
    const startTime = Date.now();
    
    try {
      await this.simulateNodeExecution(node, context);
      
      const result = {
        success: true,
        result: `输入节点 ${node.data.label} 执行成功`,
        duration: Date.now() - startTime,
        output: `输入数据: ${node.data.label}`
      };

      return result;
    } catch (error) {
      return {
        success: false,
        error: error instanceof Error ? error.message : '未知错误',
        duration: Date.now() - startTime
      };
    }
  }

  private async executeOutputNode(node: FlowNode, context: ExecutionContext): Promise<NodeExecutionResult> {
    const startTime = Date.now();
    
    try {
      await this.simulateNodeExecution(node, context);
      
      const result = {
        success: true,
        result: `输出节点 ${node.data.label} 执行成功`,
        duration: Date.now() - startTime,
        output: `输出结果: ${node.data.label}`
      };

      return result;
    } catch (error) {
      return {
        success: false,
        error: error instanceof Error ? error.message : '未知错误',
        duration: Date.now() - startTime
      };
    }
  }

  // 模拟节点执行（用于演示）
  private async simulateNodeExecution(node: FlowNode, context: ExecutionContext): Promise<void> {
    // 模拟执行时间
    const executionTime = Math.random() * 2000 + 500; // 500-2500ms
    
    // 模拟进度更新
    const progressInterval = setInterval(() => {
      if (this.executionState.currentNodeId === node.id) {
        const currentStatus = this.executionState.nodeStatuses.find(n => n.nodeId === node.id);
        if (currentStatus && currentStatus.status === 'running') {
          const progress = Math.min(100, (Date.now() - (currentStatus.startTime || 0)) / executionTime * 100);
          currentStatus.progress = Math.round(progress);
        }
      }
    }, 100);

    await new Promise(resolve => setTimeout(resolve, executionTime));
    clearInterval(progressInterval);

    // 模拟执行失败（10%概率）
    if (Math.random() < 0.1) {
      throw new Error(`节点 ${node.data.label} 模拟执行失败`);
    }
  }

  // 获取执行结果
  public getExecutionResults(): Map<string, any> {
    return new Map(this.executionContext.results);
  }

  // 获取执行错误
  public getExecutionErrors(): Map<string, string> {
    return new Map(this.executionContext.errors);
  }

  // 获取执行变量
  public getExecutionVariables(): Map<string, any> {
    return new Map(this.executionContext.variables);
  }

  // 设置执行变量
  public setExecutionVariable(key: string, value: any): void {
    this.executionContext.variables.set(key, value);
  }
}

export default FlowExecutionEngine; 