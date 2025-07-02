"""
MCP 설정 관리자
YAML/JSON 설정 파일 로딩, 환경변수 오버라이드, 핫 리로드 기능 제공
"""
import os
import asyncio
import threading
from pathlib import Path
from typing import Dict, Optional, Any, Callable, List
from datetime import datetime
import json

import yaml
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

from app.schemas.mcp_config import MCPConfig, MCPServerConfig
from app.core.logging import logger


class MCPConfigFileHandler(FileSystemEventHandler):
    """설정 파일 변경 감지 핸들러"""
    
    def __init__(self, config_manager: 'MCPConfigManager'):
        self.config_manager = config_manager
        self.last_modified = {}
    
    def on_modified(self, event):
        """파일 수정 이벤트 처리"""
        if event.is_directory:
            return
        
        file_path = event.src_path
        if not any(file_path.endswith(ext) for ext in ['.yaml', '.yml', '.json']):
            return
        
        # 중복 이벤트 방지 (파일 시스템에서 여러 번 발생할 수 있음)
        current_time = datetime.now().timestamp()
        if file_path in self.last_modified:
            if current_time - self.last_modified[file_path] < 1.0:  # 1초 내 중복 이벤트 무시
                return
        
        self.last_modified[file_path] = current_time
        
        # 비동기 리로드 실행
        asyncio.create_task(self.config_manager._reload_config_file(file_path))


class MCPConfigManager:
    """MCP 설정 관리자"""
    
    def __init__(self, config_path: Optional[str] = None, enable_hot_reload: bool = True):
        """
        Args:
            config_path: 설정 파일 경로 (기본값: config/mcp_servers.yaml)
            enable_hot_reload: 핫 리로드 활성화 여부
        """
        self.config_path = config_path or self._get_default_config_path()
        self.enable_hot_reload = enable_hot_reload
        
        # 설정 관리
        self.config: Optional[MCPConfig] = None
        self.config_lock = threading.RLock()
        self.reload_callbacks: List[Callable[[MCPConfig], None]] = []
        
        # 파일 감시자
        self.observer: Optional[Observer] = None
        self.file_handler: Optional[MCPConfigFileHandler] = None
        
        # 환경변수 매핑
        self.env_var_mappings = {
            "MONDAY_API_KEY": ("servers", "monday", "auth", "api_key"),
            "MONDAY_WORKSPACE_ID": ("servers", "monday", "metadata", "workspace_id"),
            "MONDAY_DEFAULT_BOARD_ID": ("servers", "monday", "metadata", "default_board_id"),
            "MCP_MONDAY_ENABLED": ("servers", "monday", "enabled"),
            "MCP_MONDAY_SERVER_URL": ("servers", "monday", "connection", "url"),
        }
    
    def _get_default_config_path(self) -> str:
        """기본 설정 파일 경로 반환"""
        # 프로젝트 루트에서 config 디렉토리 찾기
        current_dir = Path(__file__).parent
        project_root = current_dir.parent.parent  # app/core -> app -> project_root
        config_dir = project_root / "config"
        
        return str(config_dir / "mcp_servers.yaml")
    
    async def initialize(self) -> MCPConfig:
        """설정 관리자 초기화"""
        logger.info(f"MCP 설정 관리자 초기화: {self.config_path}")
        
        # 설정 파일 로드
        await self.load_config()
        
        # 핫 리로드 설정
        if self.enable_hot_reload:
            await self._setup_hot_reload()
        
        return self.config
    
    async def load_config(self) -> MCPConfig:
        """설정 파일 로드"""
        with self.config_lock:
            try:
                # 설정 파일 존재 확인
                if not os.path.exists(self.config_path):
                    logger.warning(f"설정 파일이 없습니다. 기본 설정을 생성합니다: {self.config_path}")
                    await self._create_default_config()
                
                # 파일 확장자에 따라 로더 선택
                if self.config_path.endswith(('.yaml', '.yml')):
                    raw_config = await self._load_yaml_config()
                elif self.config_path.endswith('.json'):
                    raw_config = await self._load_json_config()
                else:
                    raise ValueError(f"지원하지 않는 설정 파일 형식: {self.config_path}")
                
                # 환경변수 오버라이드 적용
                config_with_env = self._apply_env_overrides(raw_config)
                
                # Pydantic 모델로 검증
                self.config = MCPConfig(**config_with_env)
                
                logger.info(f"MCP 설정 로드 완료: {len(self.config.servers)}개 서버")
                
                # 콜백 실행
                await self._notify_config_reload()
                
                return self.config
                
            except Exception as e:
                logger.error(f"설정 파일 로드 실패: {e}")
                raise
    
    async def _load_yaml_config(self) -> Dict[str, Any]:
        """YAML 설정 파일 로드"""
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f) or {}
        except yaml.YAMLError as e:
            raise ValueError(f"YAML 파싱 오류: {e}")
        except Exception as e:
            raise ValueError(f"YAML 파일 읽기 오류: {e}")
    
    async def _load_json_config(self) -> Dict[str, Any]:
        """JSON 설정 파일 로드"""
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except json.JSONDecodeError as e:
            raise ValueError(f"JSON 파싱 오류: {e}")
        except Exception as e:
            raise ValueError(f"JSON 파일 읽기 오류: {e}")
    
    def _apply_env_overrides(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """환경변수 오버라이드 적용"""
        # 딥 카피로 원본 보호
        import copy
        config_copy = copy.deepcopy(config)
        
        for env_var, config_path in self.env_var_mappings.items():
            env_value = os.getenv(env_var)
            if env_value is not None:
                # 환경변수 값 타입 변환
                converted_value = self._convert_env_value(env_value)
                
                # 중첩된 설정 경로에 값 설정
                self._set_nested_config(config_copy, config_path, converted_value)
                
                logger.debug(f"환경변수 오버라이드: {env_var} -> {'.'.join(config_path)}")
        
        return config_copy
    
    def _convert_env_value(self, value: str) -> Any:
        """환경변수 값 타입 변환"""
        # 불린 값
        if value.lower() in ('true', 'false'):
            return value.lower() == 'true'
        
        # 숫자 값
        try:
            if '.' in value:
                return float(value)
            else:
                return int(value)
        except ValueError:
            pass
        
        # 문자열 값
        return value
    
    def _set_nested_config(self, config: Dict[str, Any], path: tuple, value: Any):
        """중첩된 설정 경로에 값 설정"""
        current = config
        
        for i, key in enumerate(path[:-1]):
            if key == "servers":
                # 서버 설정의 경우 서버 이름으로 찾기
                if i + 1 < len(path):
                    server_name = path[i + 1]
                    if "servers" not in current:
                        current["servers"] = []
                    
                    # 해당 서버 찾기 또는 생성
                    server_config = None
                    for server in current["servers"]:
                        if server.get("name") == server_name:
                            server_config = server
                            break
                    
                    if server_config is None:
                        # 새 서버 설정 생성
                        server_config = {"name": server_name}
                        current["servers"].append(server_config)
                    
                    current = server_config
                    # 서버 이름 건너뛰기
                    path = path[:i+1] + path[i+2:]
                    break
            else:
                if key not in current:
                    current[key] = {}
                current = current[key]
        
        # 마지막 키에 값 설정
        if path:
            current[path[-1]] = value
    
    async def _create_default_config(self):
        """기본 설정 파일 생성"""
        config_dir = os.path.dirname(self.config_path)
        os.makedirs(config_dir, exist_ok=True)
        
        default_config = {
            "version": "1.0",
            "global_config": {
                "enabled": True,
                "max_servers": 10,
                "auto_discovery": True,
                "log_level": "INFO"
            },
            "servers": []
        }
        
        # YAML 형식으로 저장
        with open(self.config_path, 'w', encoding='utf-8') as f:
            yaml.dump(default_config, f, default_flow_style=False, allow_unicode=True)
        
        logger.info(f"기본 설정 파일 생성: {self.config_path}")
    
    async def _setup_hot_reload(self):
        """핫 리로드 설정"""
        if not os.path.exists(self.config_path):
            return
        
        try:
            config_dir = os.path.dirname(os.path.abspath(self.config_path))
            
            self.file_handler = MCPConfigFileHandler(self)
            self.observer = Observer()
            self.observer.schedule(self.file_handler, config_dir, recursive=False)
            self.observer.start()
            
            logger.info(f"설정 파일 핫 리로드 활성화: {config_dir}")
            
        except Exception as e:
            logger.warning(f"핫 리로드 설정 실패: {e}")
    
    async def _reload_config_file(self, file_path: str):
        """설정 파일 리로드"""
        if not file_path.endswith(os.path.basename(self.config_path)):
            return
        
        try:
            logger.info(f"설정 파일 변경 감지, 리로드 중: {file_path}")
            await self.load_config()
            logger.info("설정 파일 리로드 완료")
            
        except Exception as e:
            logger.error(f"설정 파일 리로드 실패: {e}")
    
    async def _notify_config_reload(self):
        """설정 리로드 콜백 실행"""
        if not self.config or not self.reload_callbacks:
            return
        
        for callback in self.reload_callbacks:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(self.config)
                else:
                    callback(self.config)
            except Exception as e:
                logger.error(f"설정 리로드 콜백 실행 오류: {e}")
    
    def add_reload_callback(self, callback: Callable[[MCPConfig], None]):
        """설정 리로드 콜백 추가"""
        self.reload_callbacks.append(callback)
    
    def remove_reload_callback(self, callback: Callable[[MCPConfig], None]):
        """설정 리로드 콜백 제거"""
        if callback in self.reload_callbacks:
            self.reload_callbacks.remove(callback)
    
    async def save_config(self, config: MCPConfig):
        """설정을 파일에 저장"""
        with self.config_lock:
            try:
                # 임시로 핫 리로드 비활성화
                was_hot_reload = self.enable_hot_reload
                self.enable_hot_reload = False
                
                # 설정을 딕셔너리로 변환
                config_dict = config.dict()
                
                # 파일 형식에 따라 저장
                if self.config_path.endswith(('.yaml', '.yml')):
                    with open(self.config_path, 'w', encoding='utf-8') as f:
                        yaml.dump(config_dict, f, default_flow_style=False, allow_unicode=True)
                elif self.config_path.endswith('.json'):
                    with open(self.config_path, 'w', encoding='utf-8') as f:
                        json.dump(config_dict, f, indent=2, ensure_ascii=False)
                
                # 메모리의 설정 업데이트
                self.config = config
                
                logger.info(f"설정 파일 저장 완료: {self.config_path}")
                
                # 핫 리로드 다시 활성화
                self.enable_hot_reload = was_hot_reload
                
            except Exception as e:
                logger.error(f"설정 파일 저장 실패: {e}")
                raise
    
    def get_config(self) -> Optional[MCPConfig]:
        """현재 설정 반환"""
        with self.config_lock:
            return self.config
    
    def get_server_config(self, server_name: str) -> Optional[MCPServerConfig]:
        """특정 서버 설정 반환"""
        with self.config_lock:
            if not self.config:
                return None
            return self.config.get_server_by_name(server_name)
    
    def get_enabled_servers(self) -> List[MCPServerConfig]:
        """활성화된 서버 목록 반환"""
        with self.config_lock:
            if not self.config:
                return []
            return self.config.get_enabled_servers()
    
    async def update_server_config(self, server_name: str, updates: Dict[str, Any]):
        """특정 서버 설정 업데이트"""
        with self.config_lock:
            if not self.config:
                raise ValueError("설정이 로드되지 않았습니다")
            
            server_config = self.config.get_server_by_name(server_name)
            if not server_config:
                raise ValueError(f"서버를 찾을 수 없습니다: {server_name}")
            
            # 서버 설정 업데이트
            for key, value in updates.items():
                setattr(server_config, key, value)
            
            # 파일에 저장
            await self.save_config(self.config)
            
            logger.info(f"서버 설정 업데이트 완료: {server_name}")
    
    async def add_server_config(self, server_config: MCPServerConfig):
        """새 서버 설정 추가"""
        with self.config_lock:
            if not self.config:
                raise ValueError("설정이 로드되지 않았습니다")
            
            # 중복 이름 검사
            if self.config.get_server_by_name(server_config.name):
                raise ValueError(f"이미 존재하는 서버 이름입니다: {server_config.name}")
            
            # 서버 추가
            self.config.servers.append(server_config)
            
            # 파일에 저장
            await self.save_config(self.config)
            
            logger.info(f"새 서버 설정 추가: {server_config.name}")
    
    async def remove_server_config(self, server_name: str):
        """서버 설정 제거"""
        with self.config_lock:
            if not self.config:
                raise ValueError("설정이 로드되지 않았습니다")
            
            # 서버 찾기 및 제거
            for i, server in enumerate(self.config.servers):
                if server.name == server_name:
                    del self.config.servers[i]
                    break
            else:
                raise ValueError(f"서버를 찾을 수 없습니다: {server_name}")
            
            # 파일에 저장
            await self.save_config(self.config)
            
            logger.info(f"서버 설정 제거 완료: {server_name}")
    
    async def shutdown(self):
        """설정 관리자 종료"""
        if self.observer:
            self.observer.stop()
            self.observer.join()
            logger.info("설정 파일 감시자 종료")


# 싱글톤 인스턴스
_config_manager: Optional[MCPConfigManager] = None


def get_mcp_config_manager() -> MCPConfigManager:
    """MCP 설정 관리자 싱글톤 반환"""
    global _config_manager
    if _config_manager is None:
        _config_manager = MCPConfigManager()
    return _config_manager


async def initialize_mcp_config() -> MCPConfig:
    """MCP 설정 초기화"""
    config_manager = get_mcp_config_manager()
    return await config_manager.initialize()