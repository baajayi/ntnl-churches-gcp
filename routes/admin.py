"""
Admin Dashboard Routes
Web interface for managing tenants, viewing logs, and monitoring usage
"""

from flask import Blueprint, render_template, request, jsonify
from services.pinecone_service import get_pinecone_service
from services.gemini_service import get_gemini_service
from datetime import datetime, timedelta
import pytz

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')

# Get services
pinecone_service = get_pinecone_service()
gemini_service = get_gemini_service()


@admin_bp.route('/', methods=['GET'])
def dashboard():
    """Admin dashboard home page"""
    return render_template('admin/dashboard.html')


@admin_bp.route('/tenants', methods=['GET'])
def list_tenants():
    """List all tenants"""
    from app import TENANT_CONFIG
    return render_template('admin/tenants.html', tenants=TENANT_CONFIG)


@admin_bp.route('/api/tenants', methods=['GET'])
def api_list_tenants():
    """API endpoint to get tenant information"""
    from app import TENANT_CONFIG

    tenants_data = []
    for tenant_id, config in TENANT_CONFIG.items():
        # Get stats for each tenant
        pinecone_stats = pinecone_service.get_namespace_stats(
            config['pinecone_namespace']
        )

        tenants_data.append({
            'id': tenant_id,
            'name': config['name'],
            'enabled': config['enabled'],
            'rate_limit': config['rate_limit'],
            'vector_count': pinecone_stats.get('vector_count', 0)
        })

    return jsonify({
        'success': True,
        'tenants': tenants_data
    })


@admin_bp.route('/api/tenants/<tenant_id>/stats', methods=['GET'])
def api_tenant_stats(tenant_id):
    """Get detailed stats for a tenant"""
    from app import TENANT_CONFIG

    if tenant_id not in TENANT_CONFIG:
        return jsonify({
            'success': False,
            'error': 'Tenant not found'
        }), 404

    tenant_config = TENANT_CONFIG[tenant_id]

    # Get Pinecone stats
    pinecone_stats = pinecone_service.get_namespace_stats(
        tenant_config['pinecone_namespace']
    )

    # Get cache stats (if available)
    from flask import current_app
    cache_stats = current_app.cache_service.get_stats()

    # Get log stats (last 7 days)
    log_stats = current_app.logging_service.get_log_stats(
        tenant_id=tenant_id,
        days=7
    )

    return jsonify({
        'success': True,
        'tenant_id': tenant_id,
        'tenant_name': tenant_config['name'],
        'stats': {
            'pinecone': pinecone_stats,
            'cache': cache_stats,
            'logs': log_stats
        }
    })


@admin_bp.route('/logs/<tenant_id>', methods=['GET'])
def view_tenant_logs(tenant_id):
    """View logs for a specific tenant"""
    from app import TENANT_CONFIG

    if tenant_id not in TENANT_CONFIG:
        return "Tenant not found", 404

    return render_template('admin/logs.html', tenant_id=tenant_id, tenant_name=TENANT_CONFIG[tenant_id]['name'])


@admin_bp.route('/logs', methods=['GET'])
def logs_dashboard():
    """Unified logs dashboard for all tenants"""
    return render_template('admin/logs_dashboard.html')


@admin_bp.route('/api/logs/<tenant_id>', methods=['GET'])
def api_get_tenant_logs(tenant_id):
    """API endpoint to get logs for a tenant"""
    from app import TENANT_CONFIG
    from flask import current_app

    if tenant_id not in TENANT_CONFIG:
        return jsonify({
            'success': False,
            'error': 'Tenant not found'
        }), 404

    # Parse query parameters
    days = int(request.args.get('days', 1))
    event_type = request.args.get('event_type')
    severity = request.args.get('severity')
    limit = min(int(request.args.get('limit', 100)), 1000)

    start_date = datetime.now(pytz.UTC) - timedelta(days=days)

    result = current_app.logging_service.get_logs(
        tenant_id=tenant_id,
        start_date=start_date,
        event_type=event_type,
        severity=severity,
        limit=limit
    )

    return jsonify(result)


@admin_bp.route('/api/cache/clear/<tenant_id>', methods=['POST'])
def api_clear_cache(tenant_id):
    """Clear cache for a tenant"""
    from app import TENANT_CONFIG
    from flask import current_app

    if tenant_id not in TENANT_CONFIG:
        return jsonify({
            'success': False,
            'error': 'Tenant not found'
        }), 404

    success = current_app.cache_service.clear_tenant_cache(tenant_id)

    return jsonify({
        'success': success,
        'message': f'Cache cleared for tenant {tenant_id}' if success else 'Failed to clear cache'
    })


@admin_bp.route('/documents/<tenant_id>', methods=['GET'])
def view_tenant_documents(tenant_id):
    """View documents for a specific tenant"""
    from app import TENANT_CONFIG

    if tenant_id not in TENANT_CONFIG:
        return "Tenant not found", 404

    return render_template('admin/documents.html', tenant_id=tenant_id, tenant_name=TENANT_CONFIG[tenant_id]['name'])


@admin_bp.route('/api/system/health', methods=['GET'])
def api_system_health():
    """Get system health status"""
    from flask import current_app

    health = {
        'status': 'healthy',
        'components': {}
    }

    # Check Pinecone
    try:
        stats = pinecone_service.get_namespace_stats('demo')
        health['components']['pinecone'] = {
            'status': 'healthy' if stats['success'] else 'unhealthy',
            'details': stats
        }
    except Exception as e:
        health['components']['pinecone'] = {
            'status': 'unhealthy',
            'error': str(e)
        }

    # Check cache
    cache_stats = current_app.cache_service.get_stats()
    health['components']['cache'] = {
        'status': 'healthy' if cache_stats.get('enabled') else 'disabled',
        'details': cache_stats
    }

    # Check S3
    try:
        # Simple check - try to get stats
        test_stats = current_app.logging_service.get_log_stats('demo', days=1)
        health['components']['s3'] = {
            'status': 'healthy' if test_stats.get('success') else 'unhealthy',
            'details': test_stats
        }
    except Exception as e:
        health['components']['s3'] = {
            'status': 'unhealthy',
            'error': str(e)
        }

    # Overall status
    unhealthy_components = [k for k, v in health['components'].items() if v['status'] == 'unhealthy']
    if unhealthy_components:
        health['status'] = 'degraded'
        health['unhealthy_components'] = unhealthy_components

    return jsonify(health)
