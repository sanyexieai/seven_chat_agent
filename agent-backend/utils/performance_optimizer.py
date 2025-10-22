import asyncio
import time
import functools
from typing import List, Dict, Any, Optional, Callable, Union
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor
from utils.log_helper import get_logger

logger = get_logger("performance_optimizer")

class PerformanceOptimizer:
    """性能优化器，提供缓存、批量处理、异步处理等功能"""
    
    def __init__(self, max_workers: int = 4):
        self.max_workers = max_workers
        self.thread_pool = ThreadPoolExecutor(max_workers=max_workers)
        self.process_pool = ProcessPoolExecutor(max_workers=max_workers)
        self.cache = {}
        self.cache_ttl = {}
        
    def __del__(self):
        """清理资源"""
        self.thread_pool.shutdown(wait=True)
        self.process_pool.shutdown(wait=True)
    
    def cache_result(self, ttl_seconds: int = 3600):
        """缓存装饰器"""
        def decorator(func: Callable) -> Callable:
            @functools.wraps(func)
            def wrapper(*args, **kwargs):
                # 生成缓存键
                cache_key = self._generate_cache_key(func.__name__, args, kwargs)
                
                # 检查缓存
                if self._is_cache_valid(cache_key, ttl_seconds):
                    logger.debug(f"缓存命中: {cache_key}")
                    return self.cache[cache_key]
                
                # 执行函数
                result = func(*args, **kwargs)
                
                # 缓存结果
                self.cache[cache_key] = result
                self.cache_ttl[cache_key] = time.time()
                
                logger.debug(f"缓存存储: {cache_key}")
                return result
            
            return wrapper
        return decorator
    
    def _generate_cache_key(self, func_name: str, args: tuple, kwargs: dict) -> str:
        """生成缓存键"""
        key_parts = [func_name]
        
        # 添加位置参数
        for arg in args:
            if isinstance(arg, (str, int, float, bool)):
                key_parts.append(str(arg))
            elif isinstance(arg, (list, tuple)):
                key_parts.append(str(sorted(arg) if isinstance(arg, list) else arg))
            else:
                key_parts.append(str(hash(str(arg))))
        
        # 添加关键字参数
        for key, value in sorted(kwargs.items()):
            key_parts.append(f"{key}={value}")
        
        return "|".join(key_parts)
    
    def _is_cache_valid(self, cache_key: str, ttl_seconds: int) -> bool:
        """检查缓存是否有效"""
        if cache_key not in self.cache:
            return False
        
        if cache_key not in self.cache_ttl:
            return False
        
        return time.time() - self.cache_ttl[cache_key] < ttl_seconds
    
    def clear_cache(self, pattern: Optional[str] = None):
        """清除缓存"""
        if pattern:
            keys_to_remove = [key for key in self.cache.keys() if pattern in key]
            for key in keys_to_remove:
                del self.cache[key]
                del self.cache_ttl[key]
            logger.info(f"清除缓存: {len(keys_to_remove)} 个条目")
        else:
            self.cache.clear()
            self.cache_ttl.clear()
            logger.info("清除所有缓存")
    
    def batch_process(self, items: List[Any], batch_size: int = 32, 
                     process_func: Optional[Callable] = None) -> List[Any]:
        """批量处理"""
        if not items:
            return []
        
        if process_func is None:
            return items
        
        results = []
        for i in range(0, len(items), batch_size):
            batch = items[i:i + batch_size]
            batch_results = process_func(batch)
            results.extend(batch_results)
        
        logger.info(f"批量处理完成: {len(items)} 个项目，批次大小: {batch_size}")
        return results
    
    async def async_batch_process(self, items: List[Any], batch_size: int = 32,
                                 process_func: Optional[Callable] = None) -> List[Any]:
        """异步批量处理"""
        if not items:
            return []
        
        if process_func is None:
            return items
        
        results = []
        tasks = []
        
        for i in range(0, len(items), batch_size):
            batch = items[i:i + batch_size]
            task = asyncio.create_task(self._process_batch_async(batch, process_func))
            tasks.append(task)
        
        batch_results = await asyncio.gather(*tasks)
        
        for batch_result in batch_results:
            results.extend(batch_result)
        
        logger.info(f"异步批量处理完成: {len(items)} 个项目，批次大小: {batch_size}")
        return results
    
    async def _process_batch_async(self, batch: List[Any], process_func: Callable) -> List[Any]:
        """异步处理批次"""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(self.thread_pool, process_func, batch)
    
    def parallel_process(self, items: List[Any], process_func: Callable,
                        use_processes: bool = False) -> List[Any]:
        """并行处理"""
        if not items:
            return []
        
        executor = self.process_pool if use_processes else self.thread_pool
        
        with executor as pool:
            futures = [pool.submit(process_func, item) for item in items]
            results = [future.result() for future in futures]
        
        logger.info(f"并行处理完成: {len(items)} 个项目，使用{'进程' if use_processes else '线程'}")
        return results
    
    def measure_time(self, func: Callable) -> Callable:
        """时间测量装饰器"""
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            start_time = time.time()
            result = func(*args, **kwargs)
            end_time = time.time()
            
            execution_time = end_time - start_time
            logger.info(f"函数 {func.__name__} 执行时间: {execution_time:.4f} 秒")
            
            return result
        
        return wrapper
    
    def retry_on_failure(self, max_retries: int = 3, delay: float = 1.0):
        """重试装饰器"""
        def decorator(func: Callable) -> Callable:
            @functools.wraps(func)
            def wrapper(*args, **kwargs):
                last_exception = None
                
                for attempt in range(max_retries + 1):
                    try:
                        return func(*args, **kwargs)
                    except Exception as e:
                        last_exception = e
                        if attempt < max_retries:
                            logger.warning(f"函数 {func.__name__} 第 {attempt + 1} 次尝试失败: {str(e)}")
                            time.sleep(delay * (2 ** attempt))  # 指数退避
                        else:
                            logger.error(f"函数 {func.__name__} 所有重试失败")
                
                raise last_exception
            
            return wrapper
        return decorator
    
    def throttle(self, calls_per_second: float = 1.0):
        """限流装饰器"""
        def decorator(func: Callable) -> Callable:
            last_called = [0.0]
            
            @functools.wraps(func)
            def wrapper(*args, **kwargs):
                elapsed = time.time() - last_called[0]
                left_to_wait = 1.0 / calls_per_second - elapsed
                
                if left_to_wait > 0:
                    time.sleep(left_to_wait)
                
                last_called[0] = time.time()
                return func(*args, **kwargs)
            
            return wrapper
        return decorator
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """获取缓存统计信息"""
        total_items = len(self.cache)
        valid_items = sum(1 for key in self.cache.keys() if self._is_cache_valid(key, 0))
        
        return {
            "total_items": total_items,
            "valid_items": valid_items,
            "invalid_items": total_items - valid_items,
            "cache_hit_rate": valid_items / total_items if total_items > 0 else 0
        }
    
    def optimize_memory(self):
        """内存优化"""
        # 清理过期的缓存项
        current_time = time.time()
        expired_keys = []
        
        for key, timestamp in self.cache_ttl.items():
            if current_time - timestamp > 3600:  # 1小时过期
                expired_keys.append(key)
        
        for key in expired_keys:
            del self.cache[key]
            del self.cache_ttl[key]
        
        if expired_keys:
            logger.info(f"清理过期缓存: {len(expired_keys)} 个条目")
    
    def profile_function(self, func: Callable) -> Callable:
        """性能分析装饰器"""
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            start_time = time.time()
            start_memory = self._get_memory_usage()
            
            result = func(*args, **kwargs)
            
            end_time = time.time()
            end_memory = self._get_memory_usage()
            
            execution_time = end_time - start_time
            memory_delta = end_memory - start_memory
            
            logger.info(f"性能分析 - 函数: {func.__name__}")
            logger.info(f"  执行时间: {execution_time:.4f} 秒")
            logger.info(f"  内存变化: {memory_delta:.2f} MB")
            
            return result
        
        return wrapper
    
    def _get_memory_usage(self) -> float:
        """获取内存使用量（MB）"""
        try:
            import psutil
            process = psutil.Process()
            return process.memory_info().rss / 1024 / 1024
        except ImportError:
            return 0.0

# 全局性能优化器实例
performance_optimizer = PerformanceOptimizer()

# 便捷装饰器
def cached(ttl_seconds: int = 3600):
    """缓存装饰器"""
    return performance_optimizer.cache_result(ttl_seconds)

def timed(func: Callable) -> Callable:
    """时间测量装饰器"""
    return performance_optimizer.measure_time(func)

def retry(max_retries: int = 3, delay: float = 1.0):
    """重试装饰器"""
    return performance_optimizer.retry_on_failure(max_retries, delay)

def throttle(calls_per_second: float = 1.0):
    """限流装饰器"""
    return performance_optimizer.throttle(calls_per_second)

def profiled(func: Callable) -> Callable:
    """性能分析装饰器"""
    return performance_optimizer.profile_function(func)
