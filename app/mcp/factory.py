"""
MCP 서버 팩토리
설정에서 다양한 유형의 MCP 서버 생성 및 클라이언트 연결 관리
"""
import asyncio
import subprocess
import os
from typing import Tuple, Optional, Any, Dict, List
import json

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
import httpx

from app.schemas.mcp_config import MCPServerConfig, MCPServerType
from app.core.logging import logger


class MCPServerFactory:
    """MCP 서버 팩토리"""
    
    def __init__(self):
        """팩토리 초기화"""
        self.active_processes: Dict[str, subprocess.Popen] = {}
        self.http_clients: Dict[str, httpx.AsyncClient] = {}
    
    async def create_server(self, config: MCPServerConfig) -> Tuple[Optional[Any], Optional[Any]]:
        """
        설정에 따라 MCP 서버 및 클라이언트 생성
        
        Returns:
            Tuple[server_instance, client_instance]
        """
        try:
            logger.info(f"MCP 서버 생성: {config.name} ({config.type})")
            
            if config.type == MCPServerType.FASTMCP:
                return await self._create_fastmcp_server(config)
            elif config.type == MCPServerType.STDIO:
                return await self._create_stdio_server(config)
            elif config.type == MCPServerType.HTTP:
                return await self._create_http_server(config)
            elif config.type == MCPServerType.WEBSOCKET:
                return await self._create_websocket_server(config)
            elif config.type == MCPServerType.CUSTOM:
                return await self._create_custom_server(config)
            else:
                raise ValueError(f"지원하지 않는 서버 유형: {config.type}")
                
        except Exception as e:
            logger.error(f"MCP 서버 생성 실패: {config.name} - {e}")
            raise
    
    async def _create_fastmcp_server(self, config: MCPServerConfig) -> Tuple[Optional[Any], Optional[Any]]:
        """FastMCP 서버 생성"""
        try:
            # FastMCP는 기본적으로 Python 모듈로 실행
            if not config.connection.command:
                raise ValueError("FastMCP 서버는 실행 명령이 필요합니다")
            
            # 환경변수 준비
            env = os.environ.copy()
            if config.auth and config.auth.api_key:
                if config.auth.env_var:
                    env[config.auth.env_var] = config.auth.api_key
                else:
                    env['MCP_API_KEY'] = config.auth.api_key
            
            # 서버 프로세스 시작
            process = subprocess.Popen(
                config.connection.command,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=env,
                text=True
            )
            
            # 프로세스 추적
            self.active_processes[config.name] = process
            
            # STDIO 클라이언트로 연결
            server_params = StdioServerParameters(
                command=config.connection.command[0],
                args=config.connection.command[1:] if len(config.connection.command) > 1 else [],
                env=env
            )
            
            # 클라이언트 세션 생성
            stdio_client_session = stdio_client(server_params)
            client_session = await stdio_client_session.__aenter__()
            
            logger.info(f"FastMCP 서버 생성 완료: {config.name}")
            return process, client_session
            
        except Exception as e:
            # 실패 시 프로세스 정리
            if config.name in self.active_processes:
                try:
                    self.active_processes[config.name].terminate()
                    del self.active_processes[config.name]
                except:
                    pass
            raise e
    
    async def _create_stdio_server(self, config: MCPServerConfig) -> Tuple[Optional[Any], Optional[Any]]:
        """STDIO 서버 생성"""
        try:
            if not config.connection.command:
                raise ValueError("STDIO 서버는 실행 명령이 필요합니다")
            
            # 환경변수 준비
            env = os.environ.copy()
            if config.auth:
                if config.auth.api_key and config.auth.env_var:
                    env[config.auth.env_var] = config.auth.api_key
                if config.auth.headers:
                    for key, value in config.auth.headers.items():
                        env[f"MCP_HEADER_{key.upper()}"] = value
            
            # 서버 프로세스 시작
            process = subprocess.Popen(
                config.connection.command,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=env,
                text=True
            )
            
            # 프로세스 추적
            self.active_processes[config.name] = process
            
            # STDIO 클라이언트 매개변수 설정
            server_params = StdioServerParameters(
                command=config.connection.command[0],
                args=config.connection.command[1:] if len(config.connection.command) > 1 else [],
                env=env
            )
            
            # 클라이언트 세션 생성
            stdio_client_session = stdio_client(server_params)
            client_session = await stdio_client_session.__aenter__()
            
            logger.info(f"STDIO 서버 생성 완료: {config.name}")
            return process, client_session
            
        except Exception as e:
            # 실패 시 프로세스 정리
            if config.name in self.active_processes:
                try:
                    self.active_processes[config.name].terminate()
                    del self.active_processes[config.name]
                except:
                    pass
            raise e
    
    async def _create_http_server(self, config: MCPServerConfig) -> Tuple[Optional[Any], Optional[Any]]:
        """HTTP 서버 생성"""
        try:
            # URL 구성
            if config.connection.url:
                base_url = config.connection.url
            elif config.connection.host and config.connection.port:
                base_url = f"http://{config.connection.host}:{config.connection.port}"
            else:
                raise ValueError("HTTP 서버는 URL 또는 host/port가 필요합니다")
            
            # HTTP 헤더 준비
            headers = {}
            if config.auth:
                if config.auth.type == "api_key" and config.auth.api_key:
                    headers["X-API-Key"] = config.auth.api_key
                elif config.auth.type == "bearer" and config.auth.token:
                    headers["Authorization"] = f"Bearer {config.auth.token}"
                elif config.auth.headers:
                    headers.update(config.auth.headers)
            
            # HTTP 클라이언트 생성
            http_client = httpx.AsyncClient(
                base_url=base_url,
                headers=headers,
                timeout=config.connection.timeout,
                verify=True  # SSL 검증 활성화
            )
            
            # 클라이언트 추적
            self.http_clients[config.name] = http_client
            
            # 연결 테스트
            try:
                response = await http_client.get("/health", timeout=10)
                if response.status_code != 200:
                    raise Exception(f"서버 응답 오류: {response.status_code}")
            except httpx.RequestError as e:
                logger.warning(f"HTTP 서버 연결 테스트 실패: {e}")
                # 연결 테스트 실패해도 클라이언트는 생성 (서버가 나중에 시작될 수 있음)
            
            # 사용자 정의 MCP HTTP 클라이언트 래퍼 생성
            client_wrapper = MCPHTTPClientWrapper(http_client, base_url)
            
            logger.info(f"HTTP 서버 생성 완료: {config.name} - {base_url}")
            return http_client, client_wrapper
            
        except Exception as e:
            # 실패 시 클라이언트 정리
            if config.name in self.http_clients:
                try:
                    await self.http_clients[config.name].aclose()
                    del self.http_clients[config.name]
                except:
                    pass
            raise e
    
    async def _create_websocket_server(self, config: MCPServerConfig) -> Tuple[Optional[Any], Optional[Any]]:
        """WebSocket 서버 생성"""
        try:
            # WebSocket URL 구성
            if config.connection.url:
                ws_url = config.connection.url
                if ws_url.startswith("http://"):
                    ws_url = ws_url.replace("http://", "ws://")
                elif ws_url.startswith("https://"):
                    ws_url = ws_url.replace("https://", "wss://")
            elif config.connection.host and config.connection.port:
                ws_url = f"ws://{config.connection.host}:{config.connection.port}"
            else:
                raise ValueError("WebSocket 서버는 URL 또는 host/port가 필요합니다")
            
            # WebSocket 클라이언트 생성 (websockets 라이브러리 사용)
            import websockets
            
            # 연결 헤더 준비
            headers = {}
            if config.auth:
                if config.auth.type == "api_key" and config.auth.api_key:
                    headers["X-API-Key"] = config.auth.api_key
                elif config.auth.type == "bearer" and config.auth.token:
                    headers["Authorization"] = f"Bearer {config.auth.token}"
                elif config.auth.headers:
                    headers.update(config.auth.headers)
            
            # WebSocket 연결
            websocket = await websockets.connect(
                ws_url,
                extra_headers=headers,
                timeout=config.connection.timeout,
                max_size=1024*1024,  # 1MB
                max_queue=32
            )
            
            # 사용자 정의 MCP WebSocket 클라이언트 래퍼 생성
            client_wrapper = MCPWebSocketClientWrapper(websocket, ws_url)
            
            logger.info(f"WebSocket 서버 생성 완료: {config.name} - {ws_url}")
            return websocket, client_wrapper
            
        except Exception as e:
            raise e
    
    async def _create_custom_server(self, config: MCPServerConfig) -> Tuple[Optional[Any], Optional[Any]]:
        """사용자 정의 서버 생성"""
        try:
            # 메타데이터에서 사용자 정의 설정 읽기
            if not config.metadata:
                raise ValueError("사용자 정의 서버는 메타데이터가 필요합니다")
            
            custom_type = config.metadata.get("custom_type")
            
            if custom_type == "monday":
                # Monday.com 서버 (기존 구현 활용)
                return await self._create_monday_server(config)
            else:
                raise ValueError(f"지원하지 않는 사용자 정의 서버 유형: {custom_type}")
            
        except Exception as e:
            raise e
    
    async def _create_monday_server(self, config: MCPServerConfig) -> Tuple[Optional[Any], Optional[Any]]:
        """Monday.com 서버 생성 (기존 구현 활용)"""
        try:
            from app.mcp.monday_server import create_monday_server
            from app.mcp.monday_client import MondayMCPClient
            
            # Monday.com 서버 생성
            monday_server = await create_monday_server()
            
            # Monday.com 클라이언트 생성
            api_key = None
            if config.auth and config.auth.api_key:
                api_key = config.auth.api_key
            elif config.auth and config.auth.env_var:
                api_key = os.getenv(config.auth.env_var)
            
            monday_client = MondayMCPClient(api_key=api_key)
            await monday_client.initialize()
            
            logger.info(f"Monday.com 서버 생성 완료: {config.name}")
            return monday_server, monday_client
            
        except Exception as e:
            logger.error(f"Monday.com 서버 생성 실패: {e}")
            raise e
    
    async def cleanup_server(self, server_name: str, server_instance: Any, client_instance: Any):
        """서버 및 클라이언트 정리"""
        try:
            # 클라이언트 정리
            if client_instance:
                if hasattr(client_instance, 'close'):
                    await client_instance.close()
                elif hasattr(client_instance, '__aexit__'):
                    await client_instance.__aexit__(None, None, None)
            
            # HTTP 클라이언트 정리
            if server_name in self.http_clients:
                await self.http_clients[server_name].aclose()
                del self.http_clients[server_name]
            
            # 프로세스 정리
            if server_name in self.active_processes:
                process = self.active_processes[server_name]
                try:
                    process.terminate()
                    await asyncio.wait_for(
                        asyncio.create_task(self._wait_for_process(process)), 
                        timeout=5.0
                    )
                except asyncio.TimeoutError:
                    process.kill()
                    await asyncio.create_task(self._wait_for_process(process))
                finally:
                    del self.active_processes[server_name]
            
            # 서버 인스턴스 정리
            if server_instance:
                if hasattr(server_instance, 'close'):
                    if asyncio.iscoroutinefunction(server_instance.close):
                        await server_instance.close()
                    else:
                        server_instance.close()
                elif hasattr(server_instance, 'terminate'):
                    server_instance.terminate()
            
            logger.info(f"서버 정리 완료: {server_name}")
            
        except Exception as e:
            logger.error(f"서버 정리 오류: {server_name} - {e}")
    
    async def _wait_for_process(self, process: subprocess.Popen):
        """프로세스 종료 대기"""
        while process.poll() is None:
            await asyncio.sleep(0.1)
    
    async def cleanup_all(self):
        """모든 서버 및 클라이언트 정리"""
        logger.info("MCP 서버 팩토리 정리 시작")
        
        # HTTP 클라이언트 정리
        for name, client in list(self.http_clients.items()):
            try:
                await client.aclose()
            except Exception as e:
                logger.warning(f"HTTP 클라이언트 정리 오류: {name} - {e}")
        self.http_clients.clear()
        
        # 프로세스 정리
        for name, process in list(self.active_processes.items()):
            try:
                process.terminate()
                await asyncio.wait_for(
                    asyncio.create_task(self._wait_for_process(process)), 
                    timeout=5.0
                )
            except asyncio.TimeoutError:
                try:
                    process.kill()
                    await asyncio.create_task(self._wait_for_process(process))
                except Exception as e:
                    logger.warning(f"프로세스 강제 종료 오류: {name} - {e}")
            except Exception as e:
                logger.warning(f"프로세스 정리 오류: {name} - {e}")
        self.active_processes.clear()
        
        logger.info("MCP 서버 팩토리 정리 완료")


class MCPHTTPClientWrapper:
    """MCP HTTP 클라이언트 래퍼"""
    
    def __init__(self, http_client: httpx.AsyncClient, base_url: str):
        self.http_client = http_client
        self.base_url = base_url
    
    async def list_tools(self):
        """도구 목록 가져오기"""
        try:
            response = await self.http_client.post("/mcp/tools/list", json={})
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"HTTP MCP 도구 목록 요청 실패: {e}")
            return None
    
    async def call_tool(self, tool_name: str, arguments: Dict[str, Any]):
        """도구 호출"""
        try:
            response = await self.http_client.post(
                "/mcp/tools/call",
                json={"name": tool_name, "arguments": arguments}
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"HTTP MCP 도구 호출 실패: {tool_name} - {e}")
            return None
    
    async def list_resources(self):
        """리소스 목록 가져오기"""
        try:
            response = await self.http_client.post("/mcp/resources/list", json={})
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"HTTP MCP 리소스 목록 요청 실패: {e}")
            return None
    
    async def list_prompts(self):
        """프롬프트 목록 가져오기"""
        try:
            response = await self.http_client.post("/mcp/prompts/list", json={})
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"HTTP MCP 프롬프트 목록 요청 실패: {e}")
            return None
    
    async def close(self):
        """클라이언트 연결 종료"""
        await self.http_client.aclose()


class MCPWebSocketClientWrapper:
    """MCP WebSocket 클라이언트 래퍼"""
    
    def __init__(self, websocket, ws_url: str):
        self.websocket = websocket
        self.ws_url = ws_url
        self.request_id = 0
    
    async def _send_request(self, method: str, params: Dict[str, Any] = None):
        """WebSocket 요청 전송"""
        self.request_id += 1
        request = {
            "jsonrpc": "2.0",
            "id": self.request_id,
            "method": method,
            "params": params or {}
        }
        
        await self.websocket.send(json.dumps(request))
        
        # 응답 대기
        response_text = await self.websocket.recv()
        response = json.loads(response_text)
        
        if "error" in response:
            raise Exception(f"MCP 오류: {response['error']}")
        
        return response.get("result")
    
    async def list_tools(self):
        """도구 목록 가져오기"""
        try:
            return await self._send_request("tools/list")
        except Exception as e:
            logger.error(f"WebSocket MCP 도구 목록 요청 실패: {e}")
            return None
    
    async def call_tool(self, tool_name: str, arguments: Dict[str, Any]):
        """도구 호출"""
        try:
            return await self._send_request("tools/call", {
                "name": tool_name,
                "arguments": arguments
            })
        except Exception as e:
            logger.error(f"WebSocket MCP 도구 호출 실패: {tool_name} - {e}")
            return None
    
    async def list_resources(self):
        """리소스 목록 가져오기"""
        try:
            return await self._send_request("resources/list")
        except Exception as e:
            logger.error(f"WebSocket MCP 리소스 목록 요청 실패: {e}")
            return None
    
    async def list_prompts(self):
        """프롬프트 목록 가져오기"""
        try:
            return await self._send_request("prompts/list")
        except Exception as e:
            logger.error(f"WebSocket MCP 프롬프트 목록 요청 실패: {e}")
            return None
    
    async def close(self):
        """WebSocket 연결 종료"""
        await self.websocket.close()