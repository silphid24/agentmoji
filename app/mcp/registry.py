"""
MCP 서버 레지스트리
동적 서버 등록, 생명주기 관리, 상태 점검, LangChain 도구 등록
"""
import asyncio
import threading
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Set
from enum import Enum
import json

from app.schemas.mcp_config import MCPServerConfig, MCPConfig
from app.core.logging import logger


class MCPServerStatus(str, Enum):
    """MCP 서버 상태"""
    STOPPED = "stopped"           # 중지됨
    STARTING = "starting"         # 시작 중
    RUNNING = "running"          # 실행 중
    STOPPING = "stopping"        # 중지 중
    ERROR = "error"              # 오류 상태
    HEALTH_CHECK_FAILED = "health_check_failed"  # 상태 점검 실패


class MCPServerInstance:
    """MCP 서버 인스턴스"""
    
    def __init__(self, config: MCPServerConfig):
        self.config = config
        self.status = MCPServerStatus.STOPPED
        self.server_instance: Optional[Any] = None  # 실제 MCP 서버 인스턴스
        self.client: Optional[Any] = None           # MCP 클라이언트
        
        # 상태 관리
        self.start_time: Optional[datetime] = None
        self.last_health_check: Optional[datetime] = None
        self.health_check_failures = 0
        self.error_message: Optional[str] = None
        
        # 도구 및 리소스
        self.available_tools: List[Dict[str, Any]] = []
        self.available_resources: List[Dict[str, Any]] = []
        self.available_prompts: List[Dict[str, Any]] = []
        
        # 락 (동시성 제어)
        self.lock = asyncio.Lock()
    
    @property
    def is_running(self) -> bool:
        """서버가 실행 중인지 확인"""
        return self.status == MCPServerStatus.RUNNING
    
    @property
    def is_healthy(self) -> bool:
        """서버가 건강한 상태인지 확인"""
        if not self.is_running:
            return False
        
        # 상태 점검 실패 임계값 확인
        if self.health_check_failures >= self.config.health_check.failure_threshold:
            return False
        
        return True
    
    @property
    def uptime(self) -> Optional[timedelta]:
        """서버 가동 시간"""
        if self.start_time and self.is_running:
            return datetime.now() - self.start_time
        return None
    
    def get_info(self) -> Dict[str, Any]:
        """서버 정보 반환"""
        return {
            "name": self.config.name,
            "display_name": self.config.display_name or self.config.name,
            "description": self.config.description,
            "version": self.config.version,
            "type": self.config.type,
            "status": self.status,
            "enabled": self.config.enabled,
            "start_time": self.start_time.isoformat() if self.start_time else None,
            "uptime_seconds": self.uptime.total_seconds() if self.uptime else None,
            "last_health_check": self.last_health_check.isoformat() if self.last_health_check else None,
            "health_check_failures": self.health_check_failures,
            "error_message": self.error_message,
            "tools_count": len(self.available_tools),
            "resources_count": len(self.available_resources),
            "prompts_count": len(self.available_prompts),
            "is_healthy": self.is_healthy
        }


class MCPServerRegistry:
    """MCP 서버 레지스트리"""
    
    def __init__(self):
        """레지스트리 초기화"""
        self.servers: Dict[str, MCPServerInstance] = {}
        self.registry_lock = threading.RLock()
        
        # 상태 점검 관리
        self.health_check_task: Optional[asyncio.Task] = None
        self.health_check_running = False
        
        # 이벤트 콜백
        self.server_started_callbacks: List[callable] = []
        self.server_stopped_callbacks: List[callable] = []
        self.server_error_callbacks: List[callable] = []
        
        # 통계
        self.total_starts = 0
        self.total_stops = 0
        self.total_errors = 0
    
    async def initialize(self, config: MCPConfig):
        """레지스트리 초기화"""
        logger.info("MCP 서버 레지스트리 초기화")
        
        # 기존 서버들 정리
        await self.shutdown_all_servers()
        
        # 설정에서 서버들 등록
        for server_config in config.servers:
            await self.register_server(server_config)
        
        # 자동 시작 서버들 시작
        await self.start_auto_start_servers()
        
        # 상태 점검 시작
        if config.global_config.enabled:
            await self.start_health_monitoring()
        
        logger.info(f"MCP 서버 레지스트리 초기화 완료: {len(self.servers)}개 서버 등록")
    
    async def register_server(self, config: MCPServerConfig) -> bool:
        """서버 등록"""
        with self.registry_lock:
            if config.name in self.servers:
                logger.warning(f"이미 등록된 서버: {config.name}")
                return False
            
            # 서버 인스턴스 생성
            instance = MCPServerInstance(config)
            self.servers[config.name] = instance
            
            logger.info(f"MCP 서버 등록: {config.name} ({config.type})")
            return True
    
    async def unregister_server(self, server_name: str) -> bool:
        """서버 등록 해제"""
        with self.registry_lock:
            if server_name not in self.servers:
                logger.warning(f"등록되지 않은 서버: {server_name}")
                return False
            
            instance = self.servers[server_name]
            
            # 실행 중이면 중지
            if instance.is_running:
                await self.stop_server(server_name)
            
            # 레지스트리에서 제거
            del self.servers[server_name]
            
            logger.info(f"MCP 서버 등록 해제: {server_name}")
            return True
    
    async def start_server(self, server_name: str) -> bool:
        """서버 시작"""
        with self.registry_lock:
            if server_name not in self.servers:
                logger.error(f"등록되지 않은 서버: {server_name}")
                return False
            
            instance = self.servers[server_name]
        
        async with instance.lock:
            if instance.status != MCPServerStatus.STOPPED:
                logger.warning(f"서버가 이미 시작되었거나 시작 중입니다: {server_name}")
                return False
            
            try:
                logger.info(f"MCP 서버 시작: {server_name}")
                instance.status = MCPServerStatus.STARTING
                instance.error_message = None
                
                # MCP 서버 팩토리를 통해 서버 생성 및 시작
                from app.mcp.factory import MCPServerFactory
                factory = MCPServerFactory()
                
                server_instance, client = await factory.create_server(instance.config)
                
                if server_instance and client:
                    instance.server_instance = server_instance
                    instance.client = client
                    instance.status = MCPServerStatus.RUNNING
                    instance.start_time = datetime.now()
                    instance.health_check_failures = 0
                    
                    # 도구 및 리소스 발견
                    await self._discover_server_capabilities(instance)
                    
                    # 통계 업데이트
                    self.total_starts += 1
                    
                    # 콜백 실행
                    await self._notify_server_started(instance)
                    
                    logger.info(f"MCP 서버 시작 완료: {server_name}")
                    return True
                else:
                    raise Exception("서버 인스턴스 또는 클라이언트 생성 실패")
                    
            except Exception as e:
                instance.status = MCPServerStatus.ERROR
                instance.error_message = str(e)
                self.total_errors += 1
                
                logger.error(f"MCP 서버 시작 실패: {server_name} - {e}")
                await self._notify_server_error(instance, e)
                return False
    
    async def stop_server(self, server_name: str) -> bool:
        """서버 중지"""
        with self.registry_lock:
            if server_name not in self.servers:
                logger.error(f"등록되지 않은 서버: {server_name}")
                return False
            
            instance = self.servers[server_name]
        
        async with instance.lock:
            if instance.status not in [MCPServerStatus.RUNNING, MCPServerStatus.ERROR]:
                logger.warning(f"서버가 실행 중이 아닙니다: {server_name}")
                return False
            
            try:
                logger.info(f"MCP 서버 중지: {server_name}")
                instance.status = MCPServerStatus.STOPPING
                
                # 클라이언트 연결 종료
                if instance.client:
                    try:
                        await instance.client.close()
                    except Exception as e:
                        logger.warning(f"클라이언트 종료 중 오류: {e}")
                
                # 서버 인스턴스 종료
                if instance.server_instance:
                    try:
                        if hasattr(instance.server_instance, 'close'):
                            await instance.server_instance.close()
                        elif hasattr(instance.server_instance, 'stop'):
                            await instance.server_instance.stop()
                    except Exception as e:
                        logger.warning(f"서버 인스턴스 종료 중 오류: {e}")
                
                # 상태 업데이트
                instance.status = MCPServerStatus.STOPPED
                instance.server_instance = None
                instance.client = None
                instance.start_time = None
                instance.available_tools.clear()
                instance.available_resources.clear()
                instance.available_prompts.clear()
                
                # 통계 업데이트
                self.total_stops += 1
                
                # 콜백 실행
                await self._notify_server_stopped(instance)
                
                logger.info(f"MCP 서버 중지 완료: {server_name}")
                return True
                
            except Exception as e:
                instance.status = MCPServerStatus.ERROR
                instance.error_message = str(e)
                
                logger.error(f"MCP 서버 중지 실패: {server_name} - {e}")
                return False
    
    async def restart_server(self, server_name: str) -> bool:
        """서버 재시작"""
        logger.info(f"MCP 서버 재시작: {server_name}")
        
        if await self.stop_server(server_name):
            # 잠시 대기 후 재시작
            await asyncio.sleep(1)
            return await self.start_server(server_name)
        
        return False
    
    async def start_auto_start_servers(self):
        """자동 시작 서버들 시작"""
        auto_start_servers = []
        
        with self.registry_lock:
            for instance in self.servers.values():
                if instance.config.enabled and instance.config.auto_start:
                    auto_start_servers.append(instance.config.name)
        
        # 병렬로 시작
        start_tasks = [self.start_server(name) for name in auto_start_servers]
        if start_tasks:
            results = await asyncio.gather(*start_tasks, return_exceptions=True)
            
            success_count = sum(1 for result in results if result is True)
            logger.info(f"자동 시작 서버: {success_count}/{len(start_tasks)}개 성공")
    
    async def shutdown_all_servers(self):
        """모든 서버 종료"""
        server_names = list(self.servers.keys())
        
        if server_names:
            logger.info(f"모든 MCP 서버 종료: {len(server_names)}개")
            
            # 병렬로 종료
            stop_tasks = [self.stop_server(name) for name in server_names]
            await asyncio.gather(*stop_tasks, return_exceptions=True)
    
    async def _discover_server_capabilities(self, instance: MCPServerInstance):
        """서버의 도구, 리소스, 프롬프트 발견"""
        if not instance.client:
            return
        
        try:
            # 도구 목록 가져오기
            if hasattr(instance.client, 'list_tools'):
                tools_result = await instance.client.list_tools()
                if tools_result and hasattr(tools_result, 'tools'):
                    instance.available_tools = [tool.dict() for tool in tools_result.tools]
            
            # 리소스 목록 가져오기
            if hasattr(instance.client, 'list_resources'):
                resources_result = await instance.client.list_resources()
                if resources_result and hasattr(resources_result, 'resources'):
                    instance.available_resources = [resource.dict() for resource in resources_result.resources]
            
            # 프롬프트 목록 가져오기
            if hasattr(instance.client, 'list_prompts'):
                prompts_result = await instance.client.list_prompts()
                if prompts_result and hasattr(prompts_result, 'prompts'):
                    instance.available_prompts = [prompt.dict() for prompt in prompts_result.prompts]
            
            logger.info(
                f"서버 기능 발견 완료: {instance.config.name} - "
                f"도구 {len(instance.available_tools)}개, "
                f"리소스 {len(instance.available_resources)}개, "
                f"프롬프트 {len(instance.available_prompts)}개"
            )
            
        except Exception as e:
            logger.warning(f"서버 기능 발견 실패: {instance.config.name} - {e}")
    
    async def start_health_monitoring(self):
        """상태 점검 모니터링 시작"""
        if self.health_check_running:
            return
        
        self.health_check_running = True
        self.health_check_task = asyncio.create_task(self._health_check_loop())
        logger.info("MCP 서버 상태 점검 시작")
    
    async def stop_health_monitoring(self):
        """상태 점검 모니터링 중지"""
        self.health_check_running = False
        
        if self.health_check_task:
            self.health_check_task.cancel()
            try:
                await self.health_check_task
            except asyncio.CancelledError:
                pass
            self.health_check_task = None
        
        logger.info("MCP 서버 상태 점검 중지")
    
    async def _health_check_loop(self):
        """상태 점검 루프"""
        while self.health_check_running:
            try:
                await self._perform_health_checks()
                await asyncio.sleep(30)  # 30초마다 점검
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"상태 점검 루프 오류: {e}")
                await asyncio.sleep(60)  # 오류 시 1분 대기
    
    async def _perform_health_checks(self):
        """모든 서버 상태 점검 수행"""
        running_servers = []
        
        with self.registry_lock:
            for instance in self.servers.values():
                if instance.is_running and instance.config.health_check.enabled:
                    running_servers.append(instance)
        
        if not running_servers:
            return
        
        # 병렬로 상태 점검
        health_tasks = [self._check_server_health(instance) for instance in running_servers]
        await asyncio.gather(*health_tasks, return_exceptions=True)
    
    async def _check_server_health(self, instance: MCPServerInstance):
        """개별 서버 상태 점검"""
        try:
            # 상태 점검 간격 확인
            now = datetime.now()
            if (instance.last_health_check and 
                now - instance.last_health_check < timedelta(seconds=instance.config.health_check.interval)):
                return
            
            # 기본 연결 상태 확인
            is_healthy = True
            
            if instance.client:
                # 간단한 ping 또는 list_tools 호출로 연결 확인
                try:
                    if hasattr(instance.client, 'ping'):
                        await asyncio.wait_for(
                            instance.client.ping(),
                            timeout=instance.config.health_check.timeout
                        )
                    elif hasattr(instance.client, 'list_tools'):
                        await asyncio.wait_for(
                            instance.client.list_tools(),
                            timeout=instance.config.health_check.timeout
                        )
                except Exception:
                    is_healthy = False
            else:
                is_healthy = False
            
            # 상태 업데이트
            instance.last_health_check = now
            
            if is_healthy:
                instance.health_check_failures = 0
                if instance.status == MCPServerStatus.HEALTH_CHECK_FAILED:
                    instance.status = MCPServerStatus.RUNNING
                    logger.info(f"서버 상태 복구: {instance.config.name}")
            else:
                instance.health_check_failures += 1
                logger.warning(
                    f"서버 상태 점검 실패: {instance.config.name} "
                    f"({instance.health_check_failures}/{instance.config.health_check.failure_threshold})"
                )
                
                if instance.health_check_failures >= instance.config.health_check.failure_threshold:
                    instance.status = MCPServerStatus.HEALTH_CHECK_FAILED
                    await self._notify_server_error(instance, Exception("Health check failed"))
                    
                    # 자동 재시작 시도 (설정에 따라)
                    if instance.config.auto_start:
                        logger.info(f"서버 자동 재시작 시도: {instance.config.name}")
                        await self.restart_server(instance.config.name)
        
        except Exception as e:
            logger.error(f"상태 점검 오류: {instance.config.name} - {e}")
    
    # 콜백 관리
    async def _notify_server_started(self, instance: MCPServerInstance):
        """서버 시작 콜백 실행"""
        for callback in self.server_started_callbacks:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(instance)
                else:
                    callback(instance)
            except Exception as e:
                logger.error(f"서버 시작 콜백 오류: {e}")
    
    async def _notify_server_stopped(self, instance: MCPServerInstance):
        """서버 중지 콜백 실행"""
        for callback in self.server_stopped_callbacks:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(instance)
                else:
                    callback(instance)
            except Exception as e:
                logger.error(f"서버 중지 콜백 오류: {e}")
    
    async def _notify_server_error(self, instance: MCPServerInstance, error: Exception):
        """서버 오류 콜백 실행"""
        for callback in self.server_error_callbacks:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(instance, error)
                else:
                    callback(instance, error)
            except Exception as e:
                logger.error(f"서버 오류 콜백 오류: {e}")
    
    def add_server_started_callback(self, callback):
        """서버 시작 콜백 추가"""
        self.server_started_callbacks.append(callback)
    
    def add_server_stopped_callback(self, callback):
        """서버 중지 콜백 추가"""
        self.server_stopped_callbacks.append(callback)
    
    def add_server_error_callback(self, callback):
        """서버 오류 콜백 추가"""
        self.server_error_callbacks.append(callback)
    
    # 조회 메서드
    def get_server(self, server_name: str) -> Optional[MCPServerInstance]:
        """서버 인스턴스 반환"""
        with self.registry_lock:
            return self.servers.get(server_name)
    
    def get_all_servers(self) -> List[MCPServerInstance]:
        """모든 서버 목록 반환"""
        with self.registry_lock:
            return list(self.servers.values())
    
    def get_running_servers(self) -> List[MCPServerInstance]:
        """실행 중인 서버 목록 반환"""
        with self.registry_lock:
            return [instance for instance in self.servers.values() if instance.is_running]
    
    def get_healthy_servers(self) -> List[MCPServerInstance]:
        """건강한 서버 목록 반환"""
        with self.registry_lock:
            return [instance for instance in self.servers.values() if instance.is_healthy]
    
    def get_registry_stats(self) -> Dict[str, Any]:
        """레지스트리 통계 반환"""
        with self.registry_lock:
            running_count = len(self.get_running_servers())
            healthy_count = len(self.get_healthy_servers())
            
            return {
                "total_servers": len(self.servers),
                "running_servers": running_count,
                "healthy_servers": healthy_count,
                "total_starts": self.total_starts,
                "total_stops": self.total_stops,
                "total_errors": self.total_errors,
                "health_check_running": self.health_check_running
            }
    
    async def shutdown(self):
        """레지스트리 종료"""
        logger.info("MCP 서버 레지스트리 종료")
        
        # 상태 점검 중지
        await self.stop_health_monitoring()
        
        # 모든 서버 종료
        await self.shutdown_all_servers()
        
        # 레지스트리 정리
        with self.registry_lock:
            self.servers.clear()
        
        logger.info("MCP 서버 레지스트리 종료 완료")


# 싱글톤 인스턴스
_registry: Optional[MCPServerRegistry] = None


def get_mcp_registry() -> MCPServerRegistry:
    """MCP 서버 레지스트리 싱글톤 반환"""
    global _registry
    if _registry is None:
        _registry = MCPServerRegistry()
    return _registry