import asyncio
import json
import os
from loguru import logger
from abc import ABC, abstractmethod
from typing import List
import aiohttp
from bs4 import BeautifulSoup

try:
    from genie_tool.util.log_util import timer
except ImportError:
    from utils.timer_decorator import timer

# 始终使用本地模型的 Doc，确保类型一致性
from tools.builtin.deepsearch.models import Doc


class SearchBase(ABC):
    """搜索基类"""

    def __init__(self):
        self._count = int(os.getenv("SEARCH_COUNT", 10))
        self._timeout = int(os.getenv("SEARCH_TIMEOUT", 10))
        self._use_jd_gateway = os.getenv("USE_JD_SEARCH_GATEWAY", "true") == "true"

    @abstractmethod
    async def search(self, query: str, request_id: str = None, *args, **kwargs) -> List[Doc]:
        """抽象搜索方法"""
        raise NotImplementedError

    @staticmethod
    @timer()
    async def parser(docs: List[Doc], timeout: int=10, **kwargs) -> List[Doc]:
        async def _parser(source_url, timeout):
            async with aiohttp.ClientSession() as session:
                try:
                    async with session.get(source_url, timeout=timeout) as response:
                        if response.content_type.lower() in [
                                "text/html", "text/plain", "text/xml", "application/json", "application/xml", "application/octet-stream"]:
                            return await response.text()
                        else:
                            # TODO 其他类型暂时不解析
                            logger.warning(f"parser content-type[{response.content_type}] not parser: url=[{source_url}]")
                            return ""
                except UnicodeDecodeError as ude:
                    return ude.args[1].decode("gb2312", errors="ignore")
                except Exception as e:
                    logger.warning(f"parser error: url=[{source_url}] error={e}")
                    return ""
        # 使用 asyncio.gather 替代 TaskGroup（兼容 Python 3.10+）
        try:
            # Python 3.11+
            async with asyncio.TaskGroup() as tg:
                tasks = [tg.create_task(_parser(doc.link, timeout)) for doc in docs if doc.link]
            results = [BeautifulSoup(task.result(), "html.parser") for task in tasks]
        except AttributeError:
            # Python 3.10 及以下版本
            tasks = [_parser(doc.link, timeout) for doc in docs if doc.link]
            results = await asyncio.gather(*tasks)
            results = [BeautifulSoup(result, "html.parser") for result in results]
        except Exception as e:
            logger.warning(f"parser 执行失败: {e}")
            results = []
        
        # 确保 results 长度与 docs 长度匹配
        # 只处理有 link 的文档
        docs_with_link = [doc for doc in docs if doc.link]
        parsed_results = []
        
        for i, soup in enumerate(results):
            if i < len(docs_with_link):
                try:
                    soup_text = soup.get_text() if hasattr(soup, 'get_text') else str(soup)
                    # 确保结果是字符串
                    result = str(soup_text) if soup_text and len(str(soup_text).strip()) > 50 else str(soup.text) if hasattr(soup, 'text') else ""
                    parsed_results.append(result if result else "")
                except Exception as e:
                    logger.warning(f"解析文档内容失败: {e}")
                    parsed_results.append("")
        
        # 更新文档内容，确保是字符串类型
        doc_index = 0
        for doc in docs:
            if doc.link and doc_index < len(parsed_results):
                try:
                    # 确保 content 是字符串类型
                    new_content = str(parsed_results[doc_index]) if parsed_results[doc_index] else ""
                    # 如果原 content 为空或新内容更长，则更新
                    if not doc.content or len(new_content) > len(doc.content):
                        doc.content = new_content
                    doc_index += 1
                except Exception as e:
                    logger.warning(f"更新文档内容失败: {e}, doc={doc}")
                    doc_index += 1
        
        return docs

    @timer()
    async def search_and_dedup(
            self, query: str, request_id: str = None, *args, **kwargs
    ) -> List[Doc]:
        """
        搜索并去重，同时删除没有内容的文档
        """
        docs = await self.search(query=query, request_id=request_id, *args, **kwargs)
        docs = await self.parser(docs=docs)

        seen_docs = set()
        deduped_docs = []
        for doc in docs:
            if doc.content and doc.content not in seen_docs:
                deduped_docs.append(doc)
                seen_docs.add(doc.content)
        return deduped_docs


class BingSearch(SearchBase):

    def __init__(self):
        super().__init__()
        self._engine = "bing-search"
        self._url = os.getenv("BING_SEARCH_URL")
        self._api_key = os.getenv("BING_SEARCH_API_KEY")

        self.headers = {
            "Content-Type": "application/json",
        }
        self.set_auth()

    def set_auth(self):
        if self._use_jd_gateway:
            self.headers["Authorization"] = f"Bearer {self._api_key}"
        else:
            self.headers["Ocp-Apim-Subscription-Key"] = self._api_key

    def construct_body(self, query: str, request_id: str = None):
        if self._use_jd_gateway:
            return {
                "request_id": request_id,
                "model": self._engine,

                "messages": [{
                    "role": "user",
                    "content": query
                }],
                "count": self._count,
                "stream": False,
            }
        else:
            return {
                "q": query,
                "textDecorations": True
            }

    async def search(self, query: str, request_id: str = None, *args, **kwargs) -> List[Doc]:
        body = self.construct_body(query, request_id)
        async with aiohttp.ClientSession() as session:
            async with session.post(self._url, json=body, headers=self.headers, timeout=self._timeout) as response:
                try:
                    result = json.loads(await response.text())
                except (json.JSONDecodeError, Exception) as e:
                    logger.warning(f"BingSearch 解析响应失败: {e}")
                    return []
                
                items = result.get("webPages", {}).get("value", [])
                if not items:
                    return []
                
                docs = []
                for item in items:
                    try:
                        snippet = item.get("snippet", "")
                        if not snippet:
                            continue
                        
                        # 确保所有参数都是字符串类型
                        content = str(snippet) if snippet else ""
                        title = str(item.get("name", "") or "")
                        link = str(item.get("url", "") or "")
                        
                        if not content:
                            continue
                        
                        doc = Doc(
                            content=content,
                            title=title,
                            link=link,
                            doc_type="web_page",
                            data={"search_engine": self._engine},
                        )
                        docs.append(doc)
                    except Exception as e:
                        logger.warning(f"创建 Doc 对象失败: {e}, item={item}")
                        continue
                
                return docs


class JinaSearch(BingSearch):

    def __init__(self):
        super().__init__()
        self._engine = "search_pro_jina"
        self._url = os.getenv("JINA_SEARCH_URL")
        self._api_key = os.getenv("JINA_SEARCH_API_KEY")


    async def search(self, query: str, request_id: str = None, *args, **kwargs) -> List[Doc]:
        if self._use_jd_gateway:
            body = self.construct_body(query, request_id)
            async with aiohttp.ClientSession() as session:
                async with session.post(self._url, json=body, headers=self.headers, timeout=self._timeout) as response:
                    try:
                        result = json.loads(await response.text())
                    except (json.JSONDecodeError, Exception) as e:
                        logger.warning(f"JinaSearch 解析响应失败: {e}")
                        return []
                    
                    items = result.get("search_result", [])
                    if not items:
                        return []
                    
                    docs = []
                    for item in items:
                        try:
                            content = item.get("content", "")
                            if not content:
                                continue
                            
                            doc = Doc(
                                content=str(content),
                                title=str(item.get("title", "") or ""),
                                link=str(item.get("link", "") or ""),
                                doc_type="web_page",
                                data={"search_engine": self._engine},
                            )
                            docs.append(doc)
                        except Exception as e:
                            logger.warning(f"创建 Doc 对象失败: {e}, item={item}")
                            continue
                    
                    return docs
        else:
            headers = {
                "Accept": "application/json",
                "Authorization": f"Bearer {self._api_key}"
            }
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{self._url}?q={query}", headers=headers, timeout=self._timeout) as response:
                    try:
                        result = json.loads(await response.text())
                    except (json.JSONDecodeError, Exception) as e:
                        logger.warning(f"JinaSearch 解析响应失败: {e}")
                        return []
                    
                    items = result.get("data", [])
                    if not items:
                        return []
                    
                    docs = []
                    for item in items:
                        try:
                            content = item.get("content", "")
                            if not content:
                                continue
                            
                            doc = Doc(
                                content=str(content),
                                title=str(item.get("title", "") or ""),
                                link=str(item.get("url", "") or ""),
                                doc_type="web_page",
                                data={"search_engine": self._engine},
                            )
                            docs.append(doc)
                        except Exception as e:
                            logger.warning(f"创建 Doc 对象失败: {e}, item={item}")
                            continue
                    
                    return docs


class SogouSearch(JinaSearch):

    def __init__(self):
        super().__init__()
        self._engine = "search_pro_sogou"
        self._url = os.getenv("SOGOU_SEARCH_URL")
        self._api_key = os.getenv("SOGOU_SEARCH_API_KEY")


class SerperSearch(JinaSearch):

    def __init__(self):
        super().__init__()
        self._engine = "serper"
        self._url = os.getenv("SERPER_SEARCH_URL")
        self._api_key = os.getenv("SERPER_SEARCH_API_KEY")
        self.set_auth()
    
    def set_auth(self):
        self.headers["X-API-KEY"] = self._api_key

    def construct_body(self, query: str, request_id: str = None):
        return {
            "q": query,
            "count": self._count,
        }
    
    async def search(self, query: str, request_id: str = None, *args, **kwargs) -> List[Doc]:
        body = self.construct_body(query, request_id)
        async with aiohttp.ClientSession() as session:
            async with session.post(self._url, json=body, headers=self.headers, timeout=self._timeout) as response:
                try:
                    result = json.loads(await response.text())
                except (json.JSONDecodeError, Exception) as e:
                    logger.warning(f"SerperSearch 解析响应失败: {e}")
                    return []
                
                items = result.get("organic", [])
                if not items:
                    return []
                
                docs = []
                for item in items:
                    try:
                        snippet = item.get("snippet", "")
                        if not snippet:
                            continue
                        
                        doc = Doc(
                            content=str(snippet),
                            title=str(item.get("title", "") or ""),
                            link=str(item.get("link", "") or ""),
                            doc_type="web_page",
                            data={"search_engine": self._engine},
                        )
                        docs.append(doc)
                    except Exception as e:
                        logger.warning(f"创建 Doc 对象失败: {e}, item={item}")
                        continue
                
                return docs


class MixSearch(BingSearch):

    def __init__(self):
        super().__init__()
        self._engine = "mix_search"
        self._bing_engine = BingSearch()
        self._jina_engine = JinaSearch()
        self._sogou_engine = SogouSearch()
        self._serp_engine = SerperSearch()

    async def search(
            self, query: str, request_id: str = None,
            use_bing: bool = True, use_jina: bool = True, use_sogou: bool = True,
            use_serp: bool = True, *args, **kwargs) -> List[Doc]:
        assert use_bing or use_jina or use_sogou or use_serp
        engines = []
        if use_bing:
            engines.append(("bing", self._bing_engine))
        if use_jina:
            engines.append(("jina", self._jina_engine))
        if use_sogou:
            engines.append(("sogou", self._sogou_engine))
        if use_serp:
            engines.append(("serp", self._serp_engine))
        
        # 包装搜索函数，捕获单个引擎的错误
        async def safe_search(engine_name, engine):
            try:
                return await engine.search_and_dedup(query=query, request_id=request_id)
            except Exception as e:
                logger.warning(f"{engine_name} 搜索引擎执行失败: {e}")
                return []
        
        # 使用 asyncio.gather 替代 TaskGroup（兼容 Python 3.10+）
        # 使用 return_exceptions=True 确保单个引擎失败不影响其他引擎
        try:
            # Python 3.11+ 尝试使用 TaskGroup
            try:
                async with asyncio.TaskGroup() as tg:
                    tasks = [tg.create_task(safe_search(name, engine)) for name, engine in engines]
                results = [task.result() for task in tasks]
            except Exception as e:
                # TaskGroup 中任何任务失败都会抛出异常，回退到顺序执行
                logger.warning(f"TaskGroup 执行失败，回退到顺序执行: {e}")
                results = []
                for name, engine in engines:
                    try:
                        result = await safe_search(name, engine)
                        results.append(result)
                    except Exception as err:
                        logger.warning(f"{name} 搜索引擎执行失败: {err}")
                        results.append([])
        except AttributeError:
            # Python 3.10 及以下版本，使用 gather 并捕获异常
            tasks = [safe_search(name, engine) for name, engine in engines]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            # 过滤掉异常结果
            filtered_results = []
            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    logger.warning(f"{engines[i][0]} 搜索引擎执行失败: {result}")
                    filtered_results.append([])
                else:
                    filtered_results.append(result)
            results = filtered_results
        
        return [doc for docs in results for doc in docs]

