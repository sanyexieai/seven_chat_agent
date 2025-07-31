from typing import Dict, Any, AsyncGenerator, List
from agents.base_agent import BaseAgent
from models.chat_models import AgentMessage, StreamChunk, MessageType
from tools.report_tools import DataAnalysisTool, ReportGeneratorTool
from utils.log_helper import get_logger

# 获取logger实例
logger = get_logger("report_agent")
import asyncio
import json

class ReportAgent(BaseAgent):
    """报告智能体"""
    
    def __init__(self, name: str, description: str):
        super().__init__(name, description)
        self.system_prompt = """你是一个专业的报告生成智能体。
你的任务是分析用户的需求，收集相关信息，生成结构化的报告。
报告应该包含清晰的标题、摘要、正文和结论。"""
        
        # 添加报告工具
        self.add_tool(DataAnalysisTool())
        self.add_tool(ReportGeneratorTool())
    
    async def process_message(self, user_id: str, message: str, context: Dict[str, Any] = None) -> AgentMessage:
        """处理用户消息"""
        try:
            # 分析报告需求
            report_requirements = self._analyze_report_requirements(message)
            
            # 收集数据
            data = await self._collect_data(report_requirements)
            
            # 生成报告
            report_content = await self._generate_report(report_requirements, data)
            
            # 创建响应消息
            response = self.create_message(
                content=report_content,
                message_type=MessageType.AGENT,
                agent_name=self.name
            )
            
            # 更新上下文
            user_context = self.get_context(user_id)
            user_context.messages.append(response)
            self.update_context(user_id, user_context)
            
            return response
            
        except Exception as e:
            logger.error(f"报告智能体处理消息失败: {str(e)}")
            return self.create_message(
                content=f"生成报告时出现了问题: {str(e)}",
                message_type=MessageType.AGENT,
                agent_name=self.name
            )
    
    async def process_message_stream(self, user_id: str, message: str, context: Dict[str, Any] = None) -> AsyncGenerator[StreamChunk, None]:
        """流式处理用户消息"""
        try:
            # 分析报告需求
            report_requirements = self._analyze_report_requirements(message)
            
            # 发送开始生成信号
            yield StreamChunk(
                type="status",
                content="正在分析您的需求...",
                agent_name=self.name
            )
            
            # 收集数据
            yield StreamChunk(
                type="status",
                content="正在收集相关数据...",
                agent_name=self.name
            )
            data = await self._collect_data(report_requirements)
            
            # 生成报告
            yield StreamChunk(
                type="status",
                content="正在生成报告...",
                agent_name=self.name
            )
            report_content = await self._generate_report(report_requirements, data)
            
            # 流式输出报告
            sections = report_content.split("\n\n")
            for section in sections:
                yield StreamChunk(
                    type="content",
                    content=section + "\n\n",
                    agent_name=self.name
                )
                await asyncio.sleep(0.1)
            
            # 发送完成信号
            yield StreamChunk(
                type="final",
                content="",
                agent_name=self.name
            )
            
        except Exception as e:
            logger.error(f"报告智能体流式处理消息失败: {str(e)}")
            yield StreamChunk(
                type="error",
                content=f"生成报告时出现了问题: {str(e)}",
                agent_name=self.name
            )
    
    def _analyze_report_requirements(self, message: str) -> Dict[str, Any]:
        """分析报告需求"""
        requirements = {
            "type": "general",  # general, analysis, summary, comparison
            "topic": "",
            "sections": [],
            "data_sources": [],
            "format": "text"  # text, markdown, html
        }
        
        # 提取主题
        topic_keywords = ["关于", "分析", "总结", "报告", "关于", "report", "analysis", "summary"]
        for keyword in topic_keywords:
            if keyword in message:
                # 提取主题内容
                parts = message.split(keyword)
                if len(parts) > 1:
                    requirements["topic"] = parts[1].strip()
                break
        
        # 判断报告类型
        if any(word in message.lower() for word in ["分析", "analysis", "数据分析"]):
            requirements["type"] = "analysis"
        elif any(word in message.lower() for word in ["总结", "summary", "概括"]):
            requirements["type"] = "summary"
        elif any(word in message.lower() for word in ["比较", "对比", "comparison"]):
            requirements["type"] = "comparison"
        
        # 确定报告章节
        if requirements["type"] == "analysis":
            requirements["sections"] = ["摘要", "背景", "数据分析", "结论", "建议"]
        elif requirements["type"] == "summary":
            requirements["sections"] = ["摘要", "主要内容", "关键点", "结论"]
        else:
            requirements["sections"] = ["摘要", "背景", "内容", "结论"]
        
        return requirements
    
    async def _collect_data(self, requirements: Dict[str, Any]) -> Dict[str, Any]:
        """收集数据"""
        data = {
            "topic": requirements["topic"],
            "sources": [],
            "analysis_results": {},
            "summary": ""
        }
        
        try:
            # 使用数据分析工具
            analysis_tool = next((tool for tool in self.tools if isinstance(tool, DataAnalysisTool)), None)
            if analysis_tool:
                analysis_result = await analysis_tool.execute({
                    "topic": requirements["topic"],
                    "type": requirements["type"]
                })
                data["analysis_results"] = analysis_result
            
        except Exception as e:
            logger.error(f"数据收集失败: {str(e)}")
            data["error"] = str(e)
        
        return data
    
    async def _generate_report(self, requirements: Dict[str, Any], data: Dict[str, Any]) -> str:
        """生成报告"""
        try:
            # 使用报告生成工具
            report_tool = next((tool for tool in self.tools if isinstance(tool, ReportGeneratorTool)), None)
            if report_tool:
                report_content = await report_tool.execute({
                    "requirements": requirements,
                    "data": data
                })
                return report_content
            else:
                # 手动生成报告
                return self._generate_manual_report(requirements, data)
                
        except Exception as e:
            logger.error(f"报告生成失败: {str(e)}")
            return f"报告生成失败: {str(e)}"
    
    def _generate_manual_report(self, requirements: Dict[str, Any], data: Dict[str, Any]) -> str:
        """手动生成报告"""
        report_lines = []
        
        # 标题
        report_lines.append(f"# {requirements['topic']} 报告")
        report_lines.append("")
        
        # 摘要
        report_lines.append("## 摘要")
        report_lines.append(f"本报告对 {requirements['topic']} 进行了详细分析。")
        report_lines.append("")
        
        # 背景
        report_lines.append("## 背景")
        report_lines.append(f"随着技术的发展和需求的变化，{requirements['topic']} 变得越来越重要。")
        report_lines.append("")
        
        # 内容
        report_lines.append("## 主要内容")
        if "analysis_results" in data and data["analysis_results"]:
            report_lines.append("根据分析结果，主要发现包括：")
            for key, value in data["analysis_results"].items():
                report_lines.append(f"- {key}: {value}")
        else:
            report_lines.append("基于当前可用的信息，我们进行了全面的分析。")
        report_lines.append("")
        
        # 结论
        report_lines.append("## 结论")
        report_lines.append(f"通过对 {requirements['topic']} 的深入分析，我们得出以下结论：")
        report_lines.append("- 需要进一步的研究和验证")
        report_lines.append("- 建议采取相应的措施")
        report_lines.append("")
        
        return "\n".join(report_lines)
    
    def get_capabilities(self) -> Dict[str, Any]:
        """获取智能体能力"""
        return {
            "name": self.name,
            "description": self.description,
            "capabilities": [
                "需求分析",
                "数据收集",
                "报告生成",
                "多种格式输出"
            ],
            "tools": self.get_available_tools()
        } 