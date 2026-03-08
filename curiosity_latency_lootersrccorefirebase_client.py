"""
Firebase Firestore client with connection pooling, exponential backoff retry logic,
and real-time stream management for Project Latency Looter.

Architectural Choice: Firebase Firestore over traditional databases because:
1. Real-time streams eliminate polling overhead (critical for latency-sensitive trading)
2. Serverless scaling matches unpredictable opportunity frequency
3. Built-in offline persistence and automatic reconnection
4. Strong consistency model with ACID transactions
"""

import asyncio
import json
import time
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, AsyncGenerator
from google.cloud import firestore
from google.cloud.firestore_v1 import DocumentSnapshot
from google.cloud.firestore_v1.base_query import FieldFilter
from google.api_core.exceptions import (
    GoogleAPICallError, 
    RetryError, 
    DeadlineExceeded,
    ServiceUnavailable
)
from tenacity import (
    retry, 
    stop_after_attempt, 
    wait_exponential, 
    retry_if_exception_type,
    before_sleep_log
)
import logging

from config.settings import settings, FirestoreCollections
from src.utils.logging_setup import get_logger

logger = get_logger(__name__)

class FirebaseClient:
    """Singleton Firebase Firestore client with resilience patterns."""
    
    _instance = None
    _client = None
    _connected = False
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(FirebaseClient, cls).__new__(cls)
        return cls._instance
    
    def __init__(self):
        if not self._connected:
            self._initialize_client()
    
    def _initialize_client(self) -> None:
        """Initialize Firebase client with credentials."""
        try:
            import firebase_admin
            from firebase_admin import credentials
            
            # Initialize Firebase Admin SDK
            if not firebase_admin._apps:
                cred = credentials.Certificate(str(settings.FIREBASE_CREDENTIALS_PATH))
                firebase_admin.initialize_app(cred, {
                    'projectId': settings.FIREBASE_PROJECT_ID
                })
            
            self._client = firestore.AsyncClient()
            self._connected = True
            logger.info(f"✅ Firebase Firestore client initialized for project: {settings.FIREBASE_PROJECT_ID}")
            
        except FileNotFoundError as e:
            logger.error(f"❌ Firebase credentials not found: {e}")
            raise
        except ValueError as e:
            logger.error(f"❌ Firebase initialization error: {e}")
            raise
        except Exception as e:
            logger.error(f"❌ Unexpected Firebase initialization error: {e}")
            raise
    
    @retry(
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=1, min=4, max=60),
        retry=retry_if_exception_type((GoogleAPICallError, ServiceUnavailable, DeadlineExceeded)),
        before_sleep=before_sleep_log(logger, logging.WARNING)
    )
    async def set_document(self, collection: str, document_id: str, data: Dict[str, Any]) -> bool:
        """
        Set document with retry logic and exponential backoff.
        
        Args:
            collection: Firestore collection name
            document_id: Document ID
            data: Document data
        
        Returns:
            Success status
        """
        if not self._connected:
            self._initialize_client()
        
        try:
            doc_ref = self._client.collection(collection).document(document_id)
            await doc_ref.set(data)
            logger.debug(f"📝 Document set: {collection}/{document_id}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to set document {collection}/{document_id}: {e}")
            raise
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        retry=retry_if_exception_type((GoogleAPICallError, ServiceUnavailable))
    )
    async def get_document(self, collection: str, document_id: str) -> Optional[Dict[str, Any]]:
        """Get document with retry logic."""
        if not self._connected:
            self._initialize_client()
        
        try:
            doc_ref = self._client.collection(collection).document(document_id)
            doc = await doc_ref.get()
            
            if doc.exists:
                return {**doc.to_dict(), '_id': doc.id}
            return None
            
        except Exception as e:
            logger.error(f"❌ Failed to get document {collection}/{document_id}: {e}")
            raise
    
    async def update_system_health(self, component: str, status: str, details: Dict[str, Any] = None) -> None:
        """
        Update system health status in Firestore with timestamp.
        
        Args:
            component: Component name (e.g., 'blockchain_listener', 'arbitrage_engine')
            status: Health status ('healthy', 'degraded', 'unhealthy')
            details: Optional diagnostic details
        """
        health_data = {
            'component': component,
            'status': status,
            'timestamp': firestore.SERVER_TIMESTAMP,
            'last_updated': datetime.utcnow().isoformat(),
            'details': details or {}
        }
        
        try:
            await self.set_document(
                FirestoreCollections.SYSTEM_HEALTH,
                component,
                health_data
            )
            logger.info(f"🏥 Health updated: {component} -> {status}")
            
        except Exception as e:
            logger.error(f"❌ Failed to update health for {component}: {e}")
            # Don't raise - health monitoring shouldn't crash system
    
    @asynccontextmanager
    async def transaction(self) -> AsyncGenerator[Any, None]:
        """Context manager for Firestore ACID transactions."""
        transaction = self._client.transaction()
        
        try:
            async with transaction:
                yield transaction
                logger.debug("✅ Firestore transaction committed")
        except Exception as e:
            logger.error(f"❌ Firestore transaction failed: {e}")
            raise
    
    async def cleanup_expired_opportunities(self, ttl_seconds: int = 30) -> int:
        """
        Clean up expired opportunities (TTL pattern).
        
        Args:
            ttl_seconds: Time-to-live in seconds
        
        Returns:
            Number of deleted documents
        """
        cutoff_time = datetime.utcnow() - timedelta(seconds=ttl_seconds)
        
        try:
            query = self._client.collection(FirestoreCollections.PENDING_OPPORTUNITIES).where(
                FieldFilter("created_at", "<", cutoff_time)
            )
            
            docs = query.stream()
            deleted_count = 0
            
            async for doc in