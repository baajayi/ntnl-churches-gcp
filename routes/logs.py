"""
Logs Routes
API endpoints for retrieving and searching logs from S3
"""

from flask import Blueprint, request, jsonify, g, current_app
from datetime import datetime, timedelta
import pytz

logs_bp = Blueprint('logs', __name__)


@logs_bp.route('/logs', methods=['GET'])
def get_logs():
    """
    Retrieve logs for tenant

    Query parameters:
        start_date: Start date (ISO format or YYYY-MM-DD)
        end_date: End date (ISO format or YYYY-MM-DD)
        event_type: Filter by event type
        severity: Filter by severity level
        limit: Maximum number of entries (default 100, max 1000)

    Returns:
        {
            "success": true,
            "logs": [...],
            "count": 45
        }
    """
    try:
        # Parse query parameters
        start_date_str = request.args.get('start_date')
        end_date_str = request.args.get('end_date')
        event_type = request.args.get('event_type')
        severity = request.args.get('severity')
        limit = min(int(request.args.get('limit', 100)), 1000)

        # Parse dates
        start_date = None
        end_date = None

        if start_date_str:
            try:
                start_date = datetime.fromisoformat(start_date_str.replace('Z', '+00:00'))
            except ValueError:
                try:
                    start_date = datetime.strptime(start_date_str, '%Y-%m-%d')
                    start_date = start_date.replace(tzinfo=pytz.UTC)
                except ValueError:
                    return jsonify({
                        'success': False,
                        'error': 'Invalid start_date format. Use ISO format or YYYY-MM-DD'
                    }), 400

        if end_date_str:
            try:
                end_date = datetime.fromisoformat(end_date_str.replace('Z', '+00:00'))
            except ValueError:
                try:
                    end_date = datetime.strptime(end_date_str, '%Y-%m-%d')
                    end_date = end_date.replace(hour=23, minute=59, second=59, tzinfo=pytz.UTC)
                except ValueError:
                    return jsonify({
                        'success': False,
                        'error': 'Invalid end_date format. Use ISO format or YYYY-MM-DD'
                    }), 400

        # Get logs from S3
        result = current_app.logging_service.get_logs(
            tenant_id=g.tenant_id,
            start_date=start_date,
            end_date=end_date,
            event_type=event_type,
            severity=severity,
            limit=limit
        )

        if not result['success']:
            return jsonify({
                'success': False,
                'error': 'Failed to retrieve logs',
                'details': result.get('error')
            }), 500

        return jsonify(result), 200

    except Exception as e:
        return jsonify({
            'success': False,
            'error': 'Internal server error',
            'details': str(e) if current_app.debug else None
        }), 500


@logs_bp.route('/logs/stats', methods=['GET'])
def get_log_stats():
    """
    Get log statistics for tenant

    Query parameters:
        days: Number of days to analyze (default 7)

    Returns:
        {
            "success": true,
            "stats": {
                "total_logs": 1234,
                "event_types": {...},
                "severities": {...},
                "daily_counts": {...}
            }
        }
    """
    try:
        days = int(request.args.get('days', 7))
        days = min(days, 90)  # Cap at 90 days

        result = current_app.logging_service.get_log_stats(
            tenant_id=g.tenant_id,
            days=days
        )

        if not result['success']:
            return jsonify({
                'success': False,
                'error': 'Failed to retrieve log statistics',
                'details': result.get('error')
            }), 500

        return jsonify(result), 200

    except Exception as e:
        return jsonify({
            'success': False,
            'error': 'Internal server error',
            'details': str(e) if current_app.debug else None
        }), 500


@logs_bp.route('/logs/recent', methods=['GET'])
def get_recent_logs():
    """
    Get recent logs (last 24 hours)

    Query parameters:
        limit: Maximum number of entries (default 50)
        event_type: Filter by event type
        severity: Filter by severity level

    Returns:
        {
            "success": true,
            "logs": [...],
            "count": 25
        }
    """
    try:
        limit = min(int(request.args.get('limit', 50)), 500)
        event_type = request.args.get('event_type')
        severity = request.args.get('severity')

        # Get logs from last 24 hours
        start_date = datetime.now(pytz.UTC) - timedelta(days=1)

        result = current_app.logging_service.get_logs(
            tenant_id=g.tenant_id,
            start_date=start_date,
            event_type=event_type,
            severity=severity,
            limit=limit
        )

        if not result['success']:
            return jsonify({
                'success': False,
                'error': 'Failed to retrieve recent logs',
                'details': result.get('error')
            }), 500

        return jsonify(result), 200

    except Exception as e:
        return jsonify({
            'success': False,
            'error': 'Internal server error',
            'details': str(e) if current_app.debug else None
        }), 500


@logs_bp.route('/logs/errors', methods=['GET'])
def get_error_logs():
    """
    Get error and critical logs

    Query parameters:
        days: Number of days to search (default 7)
        limit: Maximum number of entries (default 100)

    Returns:
        {
            "success": true,
            "logs": [...],
            "count": 12
        }
    """
    try:
        days = int(request.args.get('days', 7))
        days = min(days, 30)
        limit = min(int(request.args.get('limit', 100)), 500)

        start_date = datetime.now(pytz.UTC) - timedelta(days=days)

        # Get error logs
        error_result = current_app.logging_service.get_logs(
            tenant_id=g.tenant_id,
            start_date=start_date,
            severity='error',
            limit=limit // 2
        )

        # Get critical logs
        critical_result = current_app.logging_service.get_logs(
            tenant_id=g.tenant_id,
            start_date=start_date,
            severity='critical',
            limit=limit // 2
        )

        if not error_result['success'] or not critical_result['success']:
            return jsonify({
                'success': False,
                'error': 'Failed to retrieve error logs'
            }), 500

        # Combine and sort by timestamp
        all_logs = error_result['logs'] + critical_result['logs']
        all_logs.sort(key=lambda x: x.get('timestamp', ''), reverse=True)

        return jsonify({
            'success': True,
            'logs': all_logs[:limit],
            'count': len(all_logs[:limit]),
            'tenant_id': g.tenant_id
        }), 200

    except Exception as e:
        return jsonify({
            'success': False,
            'error': 'Internal server error',
            'details': str(e) if current_app.debug else None
        }), 500
