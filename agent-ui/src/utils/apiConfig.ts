// API配置工具
interface ApiConfig {
  api: {
    backend_port: number;
    frontend_port: number;
    host: string;
  };
  app: {
    name: string;
    version: string;
  };
}

class ApiConfigManager {
  private static instance: ApiConfigManager;
  private config: ApiConfig | null = null;
  private apiBase: string = '';

  private constructor() {}

  public static getInstance(): ApiConfigManager {
    if (!ApiConfigManager.instance) {
      ApiConfigManager.instance = new ApiConfigManager();
    }
    return ApiConfigManager.instance;
  }

  public async initialize(): Promise<void> {
    try {
      const response = await fetch('/config/config.json');
      if (response.ok) {
        this.config = await response.json();
        this.updateApiBase();
      }
    } catch (error) {
      console.warn('无法加载配置文件，使用默认配置');
      this.useDefaultConfig();
    }
  }

  private updateApiBase(): void {
    if (!this.config) {
      this.useDefaultConfig();
      return;
    }

    const currentPort = window.location.port;
    if (currentPort === this.config.api.frontend_port.toString()) {
      // 如果前端运行在配置的端口，后端使用配置的后端端口
      this.apiBase = `http://${this.config.api.host}:${this.config.api.backend_port}`;
    } else {
      // 其他情况使用相对路径
      this.apiBase = '';
    }
  }

  private useDefaultConfig(): void {
    const currentPort = window.location.port;
    if (currentPort === '3000') {
      this.apiBase = 'http://localhost:8000';
    } else {
      this.apiBase = '';
    }
  }

  public getApiBase(): string {
    return this.apiBase;
  }

  public getConfig(): ApiConfig | null {
    return this.config;
  }
}

// 导出单例实例
export const apiConfigManager = ApiConfigManager.getInstance();

// 便捷函数
export const getApiBase = (): string => {
  return apiConfigManager.getApiBase();
};

export const getApiUrl = (endpoint: string): string => {
  const base = getApiBase();
  console.log('API配置 - 当前端口:', window.location.port);
  console.log('API配置 - 后端地址:', base);
  console.log('API配置 - 完整URL:', base ? `${base}${endpoint}` : endpoint);
  return base ? `${base}${endpoint}` : endpoint;
}; 