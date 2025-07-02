"""
MCP (Model Context Protocol) 서버 설정 스키마
동적 MCP 서버 등록 및 관리를 위한 Pydantic 모델들
"""
from typing import Dict, List, Optional, Any, Union
from enum import Enum
from pydantic import BaseModel, Field, validator


class MCPServerType(str, Enum):
    """MCP 서버 유형"""
    FASTMCP = "fastmcp"
    STDIO = "stdio"
    HTTP = "http"
    WEBSOCKET = "websocket"
    CUSTOM = "custom"


class MCPConnectionConfig(BaseModel):
    """MCP 서버 연결 설정"""
    host: Optional[str] = Field(default="localhost", description="서버 호스트")
    port: Optional[int] = Field(default=None, description="서버 포트")
    url: Optional[str] = Field(default=None, description="전체 URL (HTTP/WebSocket용)")
    command: Optional[List[str]] = Field(default=None, description="실행 명령 (STDIO용)")
    timeout: int = Field(default=30, description="연결 타임아웃 (초)")
    max_retries: int = Field(default=3, description="최대 재시도 횟수")
    retry_interval: int = Field(default=5, description="재시도 간격 (초)")


class MCPAuthConfig(BaseModel):
    """MCP 서버 인증 설정"""
    type: str = Field(default="none", description="인증 유형 (none, api_key, bearer, oauth)")
    api_key: Optional[str] = Field(default=None, description="API 키")
    token: Optional[str] = Field(default=None, description="Bearer 토큰")
    username: Optional[str] = Field(default=None, description="사용자명")
    password: Optional[str] = Field(default=None, description="비밀번호")
    headers: Optional[Dict[str, str]] = Field(default=None, description="추가 헤더")
    env_var: Optional[str] = Field(default=None, description="환경변수명 (보안용)")


class MCPToolConfig(BaseModel):
    """MCP 도구 설정"""
    name: str = Field(description="도구 이름")
    enabled: bool = Field(default=True, description="도구 활성화 여부")
    description: Optional[str] = Field(default=None, description="도구 설명")
    parameters: Optional[Dict[str, Any]] = Field(default=None, description="도구 매개변수")
    aliases: Optional[List[str]] = Field(default=None, description="도구 별칭")
    category: Optional[str] = Field(default="general", description="도구 카테고리")
    agent_types: Optional[List[str]] = Field(default=None, description="사용 가능한 에이전트 타입")


class MCPResourceConfig(BaseModel):
    """MCP 리소스 설정"""
    name: str = Field(description="리소스 이름")
    uri: str = Field(description="리소스 URI")
    mime_type: Optional[str] = Field(default=None, description="MIME 타입")
    description: Optional[str] = Field(default=None, description="리소스 설명")
    enabled: bool = Field(default=True, description="리소스 활성화 여부")


class MCPPromptConfig(BaseModel):
    """MCP 프롬프트 설정"""
    name: str = Field(description="프롬프트 이름")
    template: str = Field(description="프롬프트 템플릿")
    description: Optional[str] = Field(default=None, description="프롬프트 설명")
    arguments: Optional[List[str]] = Field(default=None, description="프롬프트 인수")
    enabled: bool = Field(default=True, description="프롬프트 활성화 여부")


class MCPServerHealthConfig(BaseModel):
    """MCP 서버 상태 점검 설정"""
    enabled: bool = Field(default=True, description="상태 점검 활성화")
    interval: int = Field(default=60, description="점검 간격 (초)")
    endpoint: Optional[str] = Field(default="/health", description="상태 점검 엔드포인트")
    timeout: int = Field(default=10, description="상태 점검 타임아웃 (초)")
    failure_threshold: int = Field(default=3, description="실패 임계값")


class MCPServerConfig(BaseModel):
    """MCP 서버 설정"""
    # 기본 정보
    name: str = Field(description="서버 이름 (고유 식별자)")
    display_name: Optional[str] = Field(default=None, description="표시 이름")
    description: Optional[str] = Field(default=None, description="서버 설명")
    version: Optional[str] = Field(default="1.0.0", description="서버 버전")
    
    # 서버 유형 및 연결
    type: MCPServerType = Field(description="서버 유형")
    connection: MCPConnectionConfig = Field(description="연결 설정")
    auth: Optional[MCPAuthConfig] = Field(default=None, description="인증 설정")
    
    # 기능 설정
    tools: Optional[List[MCPToolConfig]] = Field(default=None, description="도구 목록")
    resources: Optional[List[MCPResourceConfig]] = Field(default=None, description="리소스 목록")
    prompts: Optional[List[MCPPromptConfig]] = Field(default=None, description="프롬프트 목록")
    
    # 운영 설정
    enabled: bool = Field(default=True, description="서버 활성화 여부")
    auto_start: bool = Field(default=True, description="자동 시작 여부")
    health_check: MCPServerHealthConfig = Field(default_factory=MCPServerHealthConfig, description="상태 점검 설정")
    
    # 메타데이터
    tags: Optional[List[str]] = Field(default=None, description="서버 태그")
    metadata: Optional[Dict[str, Any]] = Field(default=None, description="추가 메타데이터")
    
    @validator('name')
    def validate_name(cls, v):
        """서버 이름 검증"""
        if not v or not v.strip():
            raise ValueError("서버 이름은 필수입니다")
        # 영문자, 숫자, 언더스코어, 하이픈만 허용
        import re
        if not re.match(r'^[a-zA-Z0-9_-]+$', v):
            raise ValueError("서버 이름은 영문자, 숫자, 언더스코어, 하이픈만 사용할 수 있습니다")
        return v
    
    @validator('connection')
    def validate_connection(cls, v, values):
        """연결 설정 검증"""
        server_type = values.get('type')
        
        if server_type == MCPServerType.HTTP or server_type == MCPServerType.WEBSOCKET:
            if not v.url and not (v.host and v.port):
                raise ValueError(f"{server_type} 서버는 URL 또는 host/port가 필요합니다")
        elif server_type == MCPServerType.STDIO:
            if not v.command:
                raise ValueError("STDIO 서버는 실행 명령이 필요합니다")
        
        return v


class MCPGlobalConfig(BaseModel):
    """MCP 전역 설정"""
    # 전역 설정
    enabled: bool = Field(default=True, description="MCP 시스템 활성화")
    max_servers: int = Field(default=10, description="최대 서버 수")
    auto_discovery: bool = Field(default=True, description="자동 서버 발견")
    
    # 로깅 설정
    log_level: str = Field(default="INFO", description="로그 레벨")
    log_file: Optional[str] = Field(default=None, description="로그 파일 경로")
    
    # 성능 설정
    tool_cache_ttl: int = Field(default=300, description="도구 캐시 TTL (초)")
    tool_cache_size: int = Field(default=1000, description="도구 캐시 크기")
    
    # 보안 설정
    allow_insecure_connections: bool = Field(default=False, description="비보안 연결 허용")
    validate_ssl: bool = Field(default=True, description="SSL 검증")
    
    @validator('log_level')
    def validate_log_level(cls, v):
        """로그 레벨 검증"""
        valid_levels = ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']
        if v.upper() not in valid_levels:
            raise ValueError(f"로그 레벨은 {valid_levels} 중 하나여야 합니다")
        return v.upper()


class MCPConfigRoot(BaseModel):
    """MCP 설정 루트 객체"""
    version: str = Field(default="1.0", description="설정 파일 버전")
    global_config: MCPGlobalConfig = Field(default_factory=MCPGlobalConfig, description="전역 설정")
    servers: List[MCPServerConfig] = Field(default_factory=list, description="MCP 서버 목록")
    
    @validator('servers')
    def validate_servers(cls, v):
        """서버 목록 검증"""
        # 서버 이름 중복 검사
        names = [server.name for server in v]
        if len(names) != len(set(names)):
            raise ValueError("서버 이름은 고유해야 합니다")
        
        # 최대 서버 수 검사는 global_config가 설정된 후에 수행
        return v
    
    def get_server_by_name(self, name: str) -> Optional[MCPServerConfig]:
        """이름으로 서버 설정 검색"""
        for server in self.servers:
            if server.name == name:
                return server
        return None
    
    def get_enabled_servers(self) -> List[MCPServerConfig]:
        """활성화된 서버 목록 반환"""
        return [server for server in self.servers if server.enabled]
    
    def get_servers_by_tag(self, tag: str) -> List[MCPServerConfig]:
        """태그로 서버 목록 검색"""
        return [
            server for server in self.servers 
            if server.tags and tag in server.tags
        ]


# 편의를 위한 타입 별칭
MCPConfig = MCPConfigRoot
ServerConfig = MCPServerConfig
ToolConfig = MCPToolConfig
ResourceConfig = MCPResourceConfig
PromptConfig = MCPPromptConfig