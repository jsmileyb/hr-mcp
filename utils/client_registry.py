# HTTP Client Registry for managing shared clients across the application
import httpx
import logging
from typing import Dict, Optional
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

class ClientRegistry:
    """
    Manages shared HTTP clients per host to avoid creating/destroying
    clients and TLS handshakes unnecessarily.
    """
    
    def __init__(self):
        self._clients: Dict[str, httpx.AsyncClient] = {}
        self._default_timeout = httpx.Timeout(connect=10, read=60, write=30, pool=30)
        self._default_limits = httpx.Limits(max_keepalive_connections=16, max_connections=64)
    
    def get_client(self, base_url: str, **kwargs) -> httpx.AsyncClient:
        """
        Get or create a shared client for the given base URL.
        
        Args:
            base_url: The base URL for the client
            **kwargs: Additional httpx.AsyncClient kwargs
            
        Returns:
            Shared AsyncClient instance for the host
        """
        # Normalize base_url to just scheme + netloc
        parsed = urlparse(base_url)
        host_key = f"{parsed.scheme}://{parsed.netloc}"
        
        if host_key not in self._clients:
            # Set defaults if not provided
            client_kwargs = {
                'base_url': host_key,
                'timeout': kwargs.get('timeout', self._default_timeout),
                'limits': kwargs.get('limits', self._default_limits),
                'http2': kwargs.get('http2', True),
                **{k: v for k, v in kwargs.items() if k not in ['timeout', 'limits', 'http2']}
            }
            
            self._clients[host_key] = httpx.AsyncClient(**client_kwargs)
            logger.debug(f"Created new shared client for {host_key}")
        
        return self._clients[host_key]
    
    def get_gia_client(self) -> Optional[httpx.AsyncClient]:
        """Get the GIA/OWUI client if it exists."""
        # This will be set by main.py
        return self._clients.get('_gia_client')
    
    def set_gia_client(self, client: httpx.AsyncClient):
        """Set the main GIA client."""
        self._clients['_gia_client'] = client
    
    async def close_all(self):
        """Close all managed clients."""
        for host, client in self._clients.items():
            try:
                await client.aclose()
                logger.debug(f"Closed client for {host}")
            except Exception as e:
                logger.warning(f"Error closing client for {host}: {e}")
        self._clients.clear()

# Global registry instance
client_registry = ClientRegistry()
