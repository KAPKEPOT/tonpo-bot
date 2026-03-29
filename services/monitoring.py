# fx/services/monitoring.py
import psutil
import platform
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
import logging
from sqlalchemy.orm import Session
import os

from database.models import SystemMetric, User, Trade, ConnectionLog
from services.cache import CacheService
from config.settings import settings

logger = logging.getLogger(__name__)


class MonitoringService:
    """
    System monitoring and metrics collection
    """
    
    def __init__(self, db_session: Session):
        self.db = db_session
        self.cache = CacheService()
        self.start_time = datetime.utcnow()
    
    def get_system_health(self) -> Dict[str, Any]:
        """Get overall system health status"""
        return {
            'status': 'healthy',
            'timestamp': datetime.utcnow().isoformat(),
            'uptime': (datetime.utcnow() - self.start_time).total_seconds(),
            'system': self._get_system_info(),
            'database': self._get_db_health(),
            'cache': self.cache.get_stats(),
            'services': self._check_services()
        }
    
    def _get_system_info(self) -> Dict[str, Any]:
        """Get system resource usage"""
        try:
            cpu_percent = psutil.cpu_percent(interval=1)
            memory = psutil.virtual_memory()
            disk = psutil.disk_usage('/')
            
            return {
                'hostname': platform.node(),
                'platform': platform.platform(),
                'python_version': platform.python_version(),
                'cpu': {
                    'percent': cpu_percent,
                    'count': psutil.cpu_count()
                },
                'memory': {
                    'total': memory.total,
                    'available': memory.available,
                    'percent': memory.percent,
                    'used': memory.used
                },
                'disk': {
                    'total': disk.total,
                    'used': disk.used,
                    'free': disk.free,
                    'percent': disk.percent
                },
                'processes': len(psutil.pids())
            }
        except Exception as e:
            logger.error(f"Failed to get system info: {e}")
            return {'error': str(e)}
    
    def _get_db_health(self) -> Dict[str, Any]:
        """Check database health"""
        try:
            # Test query
            start = datetime.utcnow()
            result = self.db.execute("SELECT 1").scalar()
            query_time = (datetime.utcnow() - start).total_seconds() * 1000
            
            # Get connection count
            connection_count = self.db.execute(
                "SELECT count(*) FROM pg_stat_activity WHERE state = 'active'"
            ).scalar() if 'postgresql' in str(self.db.bind.url) else 0
            
            return {
                'status': 'connected' if result == 1 else 'error',
                'response_time_ms': round(query_time, 2),
                'active_connections': connection_count,
                'url': str(self.db.bind.url).split('@')[-1]  # Hide credentials
            }
        except Exception as e:
            return {
                'status': 'error',
                'error': str(e)
            }
    
    def _check_services(self) -> Dict[str, str]:
        """Check external services"""
        services = {}
        
        # Check Redis
        if self.cache.redis_client:
            try:
                services['redis'] = 'healthy' if self.cache.redis_client.ping() else 'unhealthy'
            except:
                services['redis'] = 'unhealthy'
        else:
            services['redis'] = 'not_configured'
        
        return services
    
    def collect_metrics(self):
        """Collect and store system metrics"""
        try:
            health = self.get_system_health()
            
            # Store key metrics
            metrics = [
                ('cpu_usage', health['system']['cpu']['percent']),
                ('memory_usage', health['system']['memory']['percent']),
                ('disk_usage', health['system']['disk']['percent']),
                ('db_response_time', health['database'].get('response_time_ms', 0)),
                ('active_users', self.db.query(User).filter(User.is_active == True).count()),
                ('trades_24h', self._count_trades_last_24h()),
                ('failed_connections_24h', self._count_failed_connections())
            ]
            
            for name, value in metrics:
                metric = SystemMetric(
                    metric_name=name,
                    metric_value=value,
                    tags={'source': 'monitoring_service'}
                )
                self.db.add(metric)
            
            self.db.commit()
            logger.info("System metrics collected")
            
        except Exception as e:
            logger.error(f"Failed to collect metrics: {e}")
            self.db.rollback()
    
    def _count_trades_last_24h(self) -> int:
        """Count trades in last 24 hours"""
        cutoff = datetime.utcnow() - timedelta(days=1)
        return self.db.query(Trade).filter(Trade.created_at >= cutoff).count()
    
    def _count_failed_connections(self) -> int:
        """Count failed connections in last 24 hours"""
        cutoff = datetime.utcnow() - timedelta(days=1)
        return self.db.query(ConnectionLog).filter(
            ConnectionLog.created_at >= cutoff,
            ConnectionLog.status == 'failed'
        ).count()
    
    def get_metrics(self, metric_name: Optional[str] = None, 
                   hours: int = 24) -> Dict[str, List]:
        """Get historical metrics"""
        cutoff = datetime.utcnow() - timedelta(hours=hours)
        
        query = self.db.query(SystemMetric).filter(
            SystemMetric.created_at >= cutoff
        )
        
        if metric_name:
            query = query.filter(SystemMetric.metric_name == metric_name)
        
        query = query.order_by(SystemMetric.created_at)
        
        metrics = query.all()
        
        result = {}
        for metric in metrics:
            if metric.metric_name not in result:
                result[metric.metric_name] = {
                    'timestamps': [],
                    'values': []
                }
            
            result[metric.metric_name]['timestamps'].append(
                metric.created_at.isoformat()
            )
            result[metric.metric_name]['values'].append(metric.metric_value)
        
        return result
    
    def get_alerts(self) -> List[Dict[str, Any]]:
        """Get active system alerts"""
        alerts = []
        
        # Check CPU
        cpu = psutil.cpu_percent(interval=1)
        if cpu > 80:
            alerts.append({
                'level': 'warning' if cpu < 90 else 'critical',
                'metric': 'cpu',
                'value': cpu,
                'message': f'CPU usage is high: {cpu}%'
            })
        
        # Check memory
        memory = psutil.virtual_memory()
        if memory.percent > 80:
            alerts.append({
                'level': 'warning' if memory.percent < 90 else 'critical',
                'metric': 'memory',
                'value': memory.percent,
                'message': f'Memory usage is high: {memory.percent}%'
            })
        
        # Check disk
        disk = psutil.disk_usage('/')
        if disk.percent > 85:
            alerts.append({
                'level': 'warning' if disk.percent < 95 else 'critical',
                'metric': 'disk',
                'value': disk.percent,
                'message': f'Disk usage is high: {disk.percent}%'
            })
        
        # Check failed connections
        failed = self._count_failed_connections()
        if failed > 10:
            alerts.append({
                'level': 'warning',
                'metric': 'connections',
                'value': failed,
                'message': f'High number of failed connections: {failed} in 24h'
            })
        
        return alerts
    
    def log_error(self, error: Exception, context: Dict[str, Any] = None):
        """Log an error for monitoring"""
        logger.error(f"Error logged: {error}", exc_info=True)

        try:
            # If the session is in a failed state from a previous exception,
            # roll it back first so we can start a clean transaction
            self.db.rollback()

            metric = SystemMetric(
                metric_name='error_count',
                metric_value=1,
                tags={
                    'error_type': error.__class__.__name__,
                    'context': str(context)
                }
            )
            self.db.add(metric)
            self.db.commit()
        except Exception as db_err:
            # Don't let error-logging errors crash the error handler
            logger.warning(f"Failed to persist error metric to DB: {db_err}")
            try:
                self.db.rollback()
            except Exception:
                pass
    
    def get_performance_report(self) -> Dict[str, Any]:
        """Generate performance report"""
        return {
            'timestamp': datetime.utcnow().isoformat(),
            'uptime_seconds': (datetime.utcnow() - self.start_time).total_seconds(),
            'system': self._get_system_info(),
            'database': self._get_db_health(),
            'cache': self.cache.get_stats(),
            'alerts': self.get_alerts(),
            'metrics_24h': self.get_metrics(hours=24),
            'summary': {
                'total_users': self.db.query(User).count(),
                'active_users': self.db.query(User).filter(User.is_active == True).count(),
                'trades_today': self._count_trades_last_24h(),
                'failed_connections': self._count_failed_connections()
            }
        }


class PerformanceTracker:
    """
    Track performance of specific operations
    """
    
    def __init__(self):
        self.operations = {}
    
    def start_operation(self, operation_id: str, metadata: Dict[str, Any] = None):
        """Start tracking an operation"""
        self.operations[operation_id] = {
            'start': datetime.utcnow(),
            'metadata': metadata or {}
        }
    
    def end_operation(self, operation_id: str, status: str = 'success') -> Dict[str, Any]:
        """End tracking and return metrics"""
        if operation_id not in self.operations:
            return {}
        
        op = self.operations[operation_id]
        duration = (datetime.utcnow() - op['start']).total_seconds()
        
        result = {
            'operation_id': operation_id,
            'duration_seconds': duration,
            'status': status,
            'metadata': op['metadata'],
            'timestamp': op['start'].isoformat()
        }
        
        # Clean up
        del self.operations[operation_id]
        
        return result
    
    def get_stats(self) -> Dict[str, Any]:
        """Get current operation stats"""
        now = datetime.utcnow()
        
        active = len(self.operations)
        if active == 0:
            return {'active_operations': 0}
        
        longest = max(
            (now - op['start']).total_seconds()
            for op in self.operations.values()
        )
        
        return {
            'active_operations': active,
            'longest_running_seconds': longest,
            'operations': [
                {
                    'id': op_id,
                    'duration': (now - op['start']).total_seconds(),
                    'metadata': op['metadata']
                }
                for op_id, op in self.operations.items()
            ]
        }