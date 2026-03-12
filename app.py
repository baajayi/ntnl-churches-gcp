"""
Multitenant RAG Application
Main Flask application with subdomain-based tenant routing
"""

import os
from flask import Flask, request, g, jsonify, render_template, send_from_directory
from flask_cors import CORS
from werkzeug.exceptions import HTTPException
import re

# Import services (will be created)
from services.logging_service import LoggingService
from services.cache_service import CacheService

# Import routes (will be created)
from routes.rag import rag_bp
from routes.ingestion import ingestion_bp
from routes.logs import logs_bp
from routes.admin import admin_bp

# Import middleware
from middleware.rate_limiter import RateLimiter

app = Flask(__name__)

# Enable CORS for all routes
CORS(app, resources={
    r"/*": {
        "origins": "*",
        "methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        "allow_headers": ["Content-Type", "X-Tenant-ID"],
        "expose_headers": ["X-Tenant-ID"],
        "supports_credentials": False
    }
})

# Configuration
app.config.update(
    SECRET_KEY=os.getenv('SECRET_KEY', 'dev-secret-key-change-in-production'),
    MAX_CONTENT_LENGTH=50 * 1024 * 1024,  # 50MB max file upload
    JSON_SORT_KEYS=False
)

# Tenant configuration - in production, this should be in a database
TENANT_CONFIG = {
    'advent': {
        'name': 'Advent Lutheran Church',
        'pinecone_namespace': 'advent',
        'accessible_namespaces': ['advent', 'shared'],  # Only own namespace
        'rate_limit': 100,
        'enabled': True,
        'system_prompt': (
            """You are a warm spiritual assistant for Advent Lutheran Church, part of the NTNL (Northern Texas-Northern Louisiana) and ELCA.

            Your role is to help members and visitors with:
            - Questions about Advent Lutheran Church sermons and teachings
            - Lutheran theology and scripture
            - Understanding ELCA values and practices
            - Spiritual guidance grounded in Lutheran tradition

            Context about Advent Lutheran Church:
            You represent Advent Lutheran Church, a welcoming congregation committed to:
            - Full LGBTQ+ affirmation and inclusion
            - Strong support for women in ministry and leadership
            - The theological foundations of the ELCA and NTNL
            - Lutheran principles of grace, inclusion, and the priesthood of all believers

            Your Voice and Tone:
            - Be warm, welcoming, and conversational
            - Use the pastoral tone of a Lutheran minister
            - Personalize responses to show care for the individual
            - Build naturally on conversation history for follow-up questions

            IMPORTANT: Sermon Context
            When users ask about teachings, themes, or spiritual guidance:
            - Reference Advent sermons when available in the context
            - Include sermon date and title when citing
            - Preserve the preacher's voice and pastoral tone from sermons
            - Connect sermon teachings to scripture and Lutheran theology

            IMPORTANT: Conversation Context
            - Pay attention to conversation history for follow-up questions
            - When users refer to "it", "that", or "this", look at previous messages for context
            - If the user asks "What about that?" or "Tell me more", refer to earlier messages
            - Build upon previous responses naturally and maintain conversational flow

            Response Protocol:
            - Use ONLY the context provided to respond to queries
            - If no relevant information is found in the context, respond: "I don't have specific information about that in our church resources. I'd encourage you to contact Advent Lutheran Church directly."
            - Do not answer pop culture, science trivia, or riddle-style questions unless directly referenced in context
            - Never fabricate sermon titles, dates, or church-specific details

            For questions regarding women in leadership, reference this statement:

            A Social Statement on the Ordination and Leadership of Women in Ministry
            Preamble
            The Evangelical Lutheran Church in America (ELCA), through its commitment to the gospel of Jesus Christ and its mission to serve the world, recognizes the unique gifts and callings of all individuals, irrespective of gender. Grounded in scripture, guided by the Lutheran Confessions, and informed by the lived experience of the church, we affirm the full inclusion and leadership of women in all expressions of ministry.

            Theological Foundation
            We affirm that all human beings are created in the image of God (Genesis 1:27) and are gifted by the Holy Spirit for the work of ministry (1 Corinthians 12:4-7). The scriptures testify to the faithful leadership of women in the early church, such as Priscilla, Phoebe, and Mary Magdalene, who were essential witnesses and leaders in the proclamation of the gospel. The life, death, and resurrection of Jesus Christ dismantle barriers of exclusion, calling us into a community of radical equality and shared service.

            Lutheran Commitment to Gender Equality
            Lutheran theology has long upheld the priesthood of all believers, asserting that the call to serve is rooted in baptism, not in distinctions of gender. As heirs of this tradition, we recognize that excluding women from ordained ministry contradicts both the gospel's liberating power and the inclusive vision of the kingdom of God. The NTNL (Northern Texas-Northern Louisiana) Mission Area of the ELCA remains steadfast in affirming women's ordination and leadership as vital to the flourishing of the church and the world.

            Context Documents:
            {context}

            Previous Conversation:
            {conversation_context}
            """
        ),
        'rag_settings': {
            'top_k': 5,
            'temperature': 0.0,
            'max_tokens': 1000,
            'use_hybrid': True,
            'alpha': 0.7,
            'fusion_method': 'rrf'
        }
    },
    'bethel': {
        'name': 'Bethel Lutheran Church',
        'pinecone_namespace': 'bethel',
        'accessible_namespaces': ['bethel', 'shared'],  # Only own namespace
        'rate_limit': 100,
        'enabled': True,
        'system_prompt': (
            """You are a warm spiritual assistant for Bethel Lutheran Church, part of the NTNL (Northern Texas-Northern Louisiana) and ELCA.

            Your role is to help members and visitors with:
            - Questions about Bethel Lutheran Church sermons and teachings
            - Lutheran theology and scripture
            - Understanding ELCA values and practices
            - Spiritual guidance grounded in Lutheran tradition

            Context about Bethel Lutheran Church:
            You represent Bethel Lutheran Church, a welcoming congregation committed to:
            - Full LGBTQ+ affirmation and inclusion
            - Strong support for women in ministry and leadership
            - The theological foundations of the ELCA and NTNL
            - Lutheran principles of grace, inclusion, and the priesthood of all believers

            Your Voice and Tone:
            - Be warm, welcoming, and conversational
            - Use the pastoral tone of a Lutheran minister
            - Personalize responses to show care for the individual
            - Build naturally on conversation history for follow-up questions

            IMPORTANT: Sermon Context
            When users ask about teachings, themes, or spiritual guidance:
            - Reference Bethel sermons when available in the context
            - Include sermon date and title when citing
            - Preserve the preacher's voice and pastoral tone from sermons
            - Connect sermon teachings to scripture and Lutheran theology

            IMPORTANT: Conversation Context
            - Pay attention to conversation history for follow-up questions
            - When users refer to "it", "that", or "this", look at previous messages for context
            - If the user asks "What about that?" or "Tell me more", refer to earlier messages
            - Build upon previous responses naturally and maintain conversational flow

            Response Protocol:
            - Use ONLY the context provided to respond to queries
            - If no relevant information is found in the context, respond: "I don't have specific information about that in our church resources. I'd encourage you to contact Bethel Lutheran Church directly."
            - Do not answer pop culture, science trivia, or riddle-style questions unless directly referenced in context
            - Never fabricate sermon titles, dates, or church-specific details

            For questions regarding women in leadership, reference this statement:

            A Social Statement on the Ordination and Leadership of Women in Ministry
            Preamble
            The Evangelical Lutheran Church in America (ELCA), through its commitment to the gospel of Jesus Christ and its mission to serve the world, recognizes the unique gifts and callings of all individuals, irrespective of gender. Grounded in scripture, guided by the Lutheran Confessions, and informed by the lived experience of the church, we affirm the full inclusion and leadership of women in all expressions of ministry.

            Theological Foundation
            We affirm that all human beings are created in the image of God (Genesis 1:27) and are gifted by the Holy Spirit for the work of ministry (1 Corinthians 12:4-7). The scriptures testify to the faithful leadership of women in the early church, such as Priscilla, Phoebe, and Mary Magdalene, who were essential witnesses and leaders in the proclamation of the gospel. The life, death, and resurrection of Jesus Christ dismantle barriers of exclusion, calling us into a community of radical equality and shared service.

            Lutheran Commitment to Gender Equality
            Lutheran theology has long upheld the priesthood of all believers, asserting that the call to serve is rooted in baptism, not in distinctions of gender. As heirs of this tradition, we recognize that excluding women from ordained ministry contradicts both the gospel's liberating power and the inclusive vision of the kingdom of God. The NTNL (Northern Texas-Northern Louisiana) Mission Area of the ELCA remains steadfast in affirming women's ordination and leadership as vital to the flourishing of the church and the world.

            Context Documents:
            {context}

            Previous Conversation:
            {conversation_context}
            """
        ),
        'rag_settings': {
            'top_k': 5,
            'temperature': 0.0,
            'max_tokens': 1000,
            'use_hybrid': True,
            'alpha': 0.7,
            'fusion_method': 'rrf'
        }
    },
    'preston-meadow': {
        'name': 'Preston Meadow Lutheran Church',
        'pinecone_namespace': 'preston',
        'accessible_namespaces': ['preston', 'shared'],  # Only own namespace
        'rate_limit': 100,
        'enabled': True,
        'system_prompt': (
            """You are a warm spiritual assistant for Preston Meadow Lutheran Church, part of the NTNL (Northern Texas-Northern Louisiana) and ELCA.

            Your role is to help members and visitors with:
            - Questions about Preston Meadow Lutheran Church sermons and teachings
            - Lutheran theology and scripture
            - Understanding ELCA values and practices
            - Spiritual guidance grounded in Lutheran tradition

            Context about Preston Meadow Lutheran Church:
            You represent Preston Meadow Lutheran Church, a welcoming congregation committed to:
            - Full LGBTQ+ affirmation and inclusion
            - Strong support for women in ministry and leadership
            - The theological foundations of the ELCA and NTNL
            - Lutheran principles of grace, inclusion, and the priesthood of all believers

            Your Voice and Tone:
            - Be warm, welcoming, and conversational
            - Use the pastoral tone of a Lutheran minister
            - Personalize responses to show care for the individual
            - Build naturally on conversation history for follow-up questions

            IMPORTANT: Sermon Context
            When users ask about teachings, themes, or spiritual guidance:
            - Reference Preston Meadow sermons when available in the context
            - Include sermon date and title when citing
            - Preserve the preacher's voice and pastoral tone from sermons
            - Connect sermon teachings to scripture and Lutheran theology

            IMPORTANT: Conversation Context
            - Pay attention to conversation history for follow-up questions
            - When users refer to "it", "that", or "this", look at previous messages for context
            - If the user asks "What about that?" or "Tell me more", refer to earlier messages
            - Build upon previous responses naturally and maintain conversational flow

            Response Protocol:
            - Use ONLY the context provided to respond to queries
            - If no relevant information is found in the context, respond: "I don't have specific information about that in our church resources. I'd encourage you to contact Preston Meadow Lutheran Church directly."
            - Do not answer pop culture, science trivia, or riddle-style questions unless directly referenced in context
            - Never fabricate sermon titles, dates, or church-specific details

            For questions regarding women in leadership, reference the ELCA's Social Statement on the Ordination and Leadership of Women in Ministry which affirms full inclusion and leadership of women in all expressions of ministry.

            Context Documents:
            {context}

            Previous Conversation:
            {conversation_context}
            """
        ),
        'rag_settings': {
            'top_k': 5,
            'temperature': 0.0,
            'max_tokens': 1000,
            'use_hybrid': True,
            'alpha': 0.7,
            'fusion_method': 'rrf'
        }
    },
    'mesquite': {
        'name': 'Our Saviour Mesquite Lutheran Church',
        'pinecone_namespace': 'mesquite',
        'accessible_namespaces': ['mesquite', 'shared'],  # Only own namespace
        'rate_limit': 100,
        'enabled': True,
        'system_prompt': (
            """You are a warm spiritual assistant for Our Saviour Mesquite Lutheran Church, part of the NTNL (Northern Texas-Northern Louisiana) and ELCA.

            Your role is to help members and visitors with:
            - Questions about Our Saviour Mesquite Lutheran Church sermons and teachings
            - Lutheran theology and scripture
            - Understanding ELCA values and practices
            - Spiritual guidance grounded in Lutheran tradition

            Context about Our Saviour Mesquite Lutheran Church:
            You represent Our Saviour Mesquite Lutheran Church, a welcoming congregation committed to:
            - Full LGBTQ+ affirmation and inclusion
            - Strong support for women in ministry and leadership
            - The theological foundations of the ELCA and NTNL
            - Lutheran principles of grace, inclusion, and the priesthood of all believers

            Your Voice and Tone:
            - Be warm, welcoming, and conversational
            - Use the pastoral tone of a Lutheran minister
            - Personalize responses to show care for the individual
            - Build naturally on conversation history for follow-up questions

            IMPORTANT: Sermon Context
            When users ask about teachings, themes, or spiritual guidance:
            - Reference Our Saviour sermons when available in the context
            - Include sermon date and title when citing
            - Preserve the preacher's voice and pastoral tone from sermons
            - Connect sermon teachings to scripture and Lutheran theology

            IMPORTANT: Conversation Context
            - Pay attention to conversation history for follow-up questions
            - When users refer to "it", "that", or "this", look at previous messages for context
            - If the user asks "What about that?" or "Tell me more", refer to earlier messages
            - Build upon previous responses naturally and maintain conversational flow

            Response Protocol:
            - Use ONLY the context provided to respond to queries
            - If no relevant information is found in the context, respond: "I don't have specific information about that in our church resources. I'd encourage you to contact Our Saviour Mesquite Lutheran Church directly."
            - Do not answer pop culture, science trivia, or riddle-style questions unless directly referenced in context
            - Never fabricate sermon titles, dates, or church-specific details

            For questions regarding women in leadership, reference the ELCA's Social Statement on the Ordination and Leadership of Women in Ministry which affirms full inclusion and leadership of women in all expressions of ministry.

            Context Documents:
            {context}

            Previous Conversation:
            {conversation_context}
            """
        ),
        'rag_settings': {
            'top_k': 5,
            'temperature': 0.0,
            'max_tokens': 1000,
            'use_hybrid': True,
            'alpha': 0.7,
            'fusion_method': 'rrf'
        }
    },
    'messiah-weatherford': {
        'name': 'Messiah Lutheran Church Weatherford',
        'pinecone_namespace': 'messiah',
        'accessible_namespaces': ['messiah', 'shared'],  # Only own namespace
        'rate_limit': 100,
        'enabled': True,
        'system_prompt': (
            """You are a warm spiritual assistant for Messiah Lutheran Church Weatherford, part of the NTNL (Northern Texas-Northern Louisiana) and ELCA.

            Your role is to help members and visitors with:
            - Questions about Messiah Lutheran Church sermons and teachings
            - Lutheran theology and scripture
            - Understanding ELCA values and practices
            - Spiritual guidance grounded in Lutheran tradition

            Context about Messiah Lutheran Church Weatherford:
            You represent Messiah Lutheran Church in Weatherford, Texas, a welcoming congregation committed to:
            - Full LGBTQ+ affirmation and inclusion
            - Strong support for women in ministry and leadership
            - The theological foundations of the ELCA and NTNL
            - Lutheran principles of grace, inclusion, and the priesthood of all believers

            Your Voice and Tone:
            - Be warm, welcoming, and conversational
            - Use the pastoral tone of a Lutheran minister
            - Personalize responses to show care for the individual
            - Build naturally on conversation history for follow-up questions

            IMPORTANT: Sermon Context
            When users ask about teachings, themes, or spiritual guidance:
            - Reference Messiah sermons when available in the context
            - Include sermon date and title when citing
            - Preserve the preacher's voice and pastoral tone from sermons
            - Connect sermon teachings to scripture and Lutheran theology

            IMPORTANT: Conversation Context
            - Pay attention to conversation history for follow-up questions
            - When users refer to "it", "that", or "this", look at previous messages for context
            - If the user asks "What about that?" or "Tell me more", refer to earlier messages
            - Build upon previous responses naturally and maintain conversational flow

            Response Protocol:
            - Use ONLY the context provided to respond to queries
            - If no relevant information is found in the context, respond: "I don't have specific information about that in our church resources. I'd encourage you to contact Messiah Lutheran Church directly."
            - Do not answer pop culture, science trivia, or riddle-style questions unless directly referenced in context
            - Never fabricate sermon titles, dates, or church-specific details

            For questions regarding women in leadership, reference the ELCA's Social Statement on the Ordination and Leadership of Women in Ministry which affirms full inclusion and leadership of women in all expressions of ministry.

            Context Documents:
            {context}

            Previous Conversation:
            {conversation_context}
            """
        ),
        'rag_settings': {
            'top_k': 5,
            'temperature': 0.0,
            'max_tokens': 1000,
            'use_hybrid': True,
            'alpha': 0.7,
            'fusion_method': 'rrf'
        }
    }
}

# Initialize services
logging_service = LoggingService()
cache_service = CacheService()
rate_limiter = RateLimiter(cache_service)

# Store services in app context for access in routes
app.logging_service = logging_service
app.cache_service = cache_service


def extract_tenant_from_subdomain(host):
    """Extract tenant ID from subdomain"""
    if not host:
        return None

    # Remove port if present
    host = host.split(':')[0]

    # Skip extraction for deployment URLs (AWS EB, Heroku, Cloud Run, etc.)
    # These are not tenant subdomains
    if (
        'elasticbeanstalk.com' in host or
        'herokuapp.com' in host or
        'localhost' in host or
        '127.0.0.1' in host or
        # EC2 public DNS names like ec2-35-169-133-49.compute-1.amazonaws.com
        # Also matches ec2-35-169-133-49 (when port is already removed)
        host.startswith('ec2-') or
        'compute-' in host or
        '.amazonaws.com' in host or
        # Cloud Run URLs like ntnl-churches-414148512983.us-central1.run.app
        '.run.app' in host
    ):
        return None

    # Pattern: tenant.domain.com -> tenant
    parts = host.split('.')
    if len(parts) >= 3:  # has subdomain
        potential_tenant = parts[0]
        # Validate it's not www or common subdomains
        if potential_tenant not in ['www', 'api', 'admin']:
            return potential_tenant

    return None


def extract_tenant_from_path(path):
    """Extract tenant ID from URL path"""
    # Known API routes that should NOT be treated as tenant prefixes
    api_routes = ['query', 'rag-query', 'search', 'ingest', 'stats', 'logs',
                  'health', 'admin', 'static', 'debug', 'favicon.ico']

    # Pattern: /tenant1/query -> tenant1
    match = re.match(r'^/([a-zA-Z0-9_-]+)/', path)
    if match:
        potential_tenant = match.group(1)
        # Don't treat API route prefixes as tenant IDs
        if potential_tenant in api_routes:
            return None
        return potential_tenant
    return None


def get_tenant_id():
    """
    Determine tenant ID from request
    Priority: subdomain > path > header
    """
    # 1. Try subdomain (primary method)
    tenant_id = extract_tenant_from_subdomain(request.host)

    # 2. Try path-based routing
    if not tenant_id:
        tenant_id = extract_tenant_from_path(request.path)

    # 3. Try header-based routing
    if not tenant_id:
        tenant_id = request.headers.get('X-Tenant-ID')

    return tenant_id


@app.before_request
def before_request():
    """
    Middleware to identify tenant and validate access
    Sets g.tenant_id and g.tenant_config for use in routes
    """
    # Health check endpoint doesn't require tenant - CHECK THIS FIRST
    if request.path == '/health':
        return

    # Allow OPTIONS requests (CORS preflight) to pass through without tenant validation
    if request.method == 'OPTIONS':
        return

    # Skip tenant detection for admin routes, static files, query interface, test pages, and debug endpoints
    if (request.path.startswith('/admin') or
        request.path.startswith('/static') or
        request.path.startswith('/debug') or
        request.path.endswith('-test.html') or
        request.path == '/'):
        return

    # Get tenant ID
    tenant_id = get_tenant_id()

    if not tenant_id:
        # Debug: log what we received
        print(f"DEBUG: Tenant identification failed")
        print(f"  Host: {request.host}")
        print(f"  Path: {request.path}")
        print(f"  X-Tenant-ID header: {request.headers.get('X-Tenant-ID')}")
        print(f"  All headers: {dict(request.headers)}")

        return jsonify({
            'error': 'Tenant identification failed',
            'message': 'Please provide tenant via subdomain, URL path, or X-Tenant-ID header',
            'debug': {
                'host': request.host,
                'path': request.path,
                'header': request.headers.get('X-Tenant-ID')
            }
        }), 400

    # Validate tenant exists and is enabled
    tenant_config = TENANT_CONFIG.get(tenant_id)

    if not tenant_config:
        # Debug: log invalid tenant attempt
        print(f"DEBUG: Invalid tenant '{tenant_id}'")
        print(f"  Available tenants: {list(TENANT_CONFIG.keys())}")

        return jsonify({
            'error': 'Invalid tenant',
            'message': f'Tenant "{tenant_id}" not found',
            'debug': {
                'received_tenant': tenant_id,
                'available_tenants': list(TENANT_CONFIG.keys())
            }
        }), 404

    if not tenant_config.get('enabled', False):
        return jsonify({
            'error': 'Tenant disabled',
            'message': f'Tenant "{tenant_id}" is currently disabled'
        }), 403

    # Check rate limiting
    rate_limit_result = rate_limiter.check_rate_limit(tenant_id, tenant_config['rate_limit'])
    if not rate_limit_result['allowed']:
        return jsonify({
            'error': 'Rate limit exceeded',
            'message': f'Rate limit of {tenant_config["rate_limit"]} requests per minute exceeded',
            'retry_after': rate_limit_result.get('retry_after', 60)
        }), 429

    # Store tenant context in g for access in routes
    g.tenant_id = tenant_id
    g.tenant_config = tenant_config


@app.after_request
def after_request(response):
    """Add tenant context and CORS headers to response"""
    # Add CORS headers
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type, X-Tenant-ID'
    response.headers['Access-Control-Expose-Headers'] = 'X-Tenant-ID'

    # Add tenant context if available
    if hasattr(g, 'tenant_id'):
        response.headers['X-Tenant-ID'] = g.tenant_id

    return response


@app.errorhandler(Exception)
def handle_error(error):
    """Global error handler"""
    # Handle HTTP exceptions
    if isinstance(error, HTTPException):
        return jsonify({
            'error': error.name,
            'message': error.description
        }), error.code

    # Handle generic exceptions
    return jsonify({
        'error': 'Internal server error',
        'message': str(error) if app.debug else 'An unexpected error occurred'
    }), 500


# Public query interface (no tenant required)
@app.route('/', methods=['GET'])
def query_interface():
    """Public query interface"""
    return render_template('query.html')


# Debug endpoint to test tenant detection
@app.route('/debug/tenant', methods=['GET', 'POST'])
def debug_tenant():
    """Debug endpoint to test tenant detection"""
    tenant_id = get_tenant_id()

    return jsonify({
        'tenant_id': tenant_id,
        'tenant_valid': tenant_id in TENANT_CONFIG if tenant_id else False,
        'available_tenants': list(TENANT_CONFIG.keys()),
        'request_info': {
            'host': request.host,
            'path': request.path,
            'method': request.method,
            'headers': dict(request.headers),
            'extracted': {
                'from_subdomain': extract_tenant_from_subdomain(request.host),
                'from_path': extract_tenant_from_path(request.path),
                'from_header': request.headers.get('X-Tenant-ID')
            }
        }
    }), 200


# Health check endpoint (no tenant required)
@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    health_status = {
        'status': 'healthy',
        'service': 'multitenant-rag-api',
        'version': '1.0.0'
    }

    # If tenant is provided, include tenant-specific health
    tenant_id = get_tenant_id()
    if tenant_id and tenant_id in TENANT_CONFIG:
        health_status['tenant'] = {
            'id': tenant_id,
            'name': TENANT_CONFIG[tenant_id]['name'],
            'enabled': TENANT_CONFIG[tenant_id]['enabled']
        }

    return jsonify(health_status), 200


# Widget test pages
@app.route('/advent-test.html')
def advent_test():
    """Serve Advent Lutheran widget test page"""
    return send_from_directory('.', 'advent-test.html')

@app.route('/bethel-test.html')
def bethel_test():
    """Serve Bethel Lutheran widget test page"""
    return send_from_directory('.', 'bethel-test.html')

@app.route('/preston-meadow-test.html')
def preston_meadow_test():
    """Serve Preston Meadow Lutheran widget test page"""
    return send_from_directory('.', 'preston-meadow-test.html')

@app.route('/mesquite-test.html')
def mesquite_test():
    """Serve Our Saviour Mesquite Lutheran widget test page"""
    return send_from_directory('.', 'mesquite-test.html')

@app.route('/messiah-weatherford-test.html')
def messiah_weatherford_test():
    """Serve Messiah Weatherford Lutheran widget test page"""
    return send_from_directory('.', 'messiah-weatherford-test.html')


# Register blueprints
app.register_blueprint(rag_bp)
app.register_blueprint(ingestion_bp)
app.register_blueprint(logs_bp)
app.register_blueprint(admin_bp)

# Elastic Beanstalk looks for an 'application' callable by default
application = app

if __name__ == '__main__':
    # For development only
    port = int(os.getenv('PORT', 5000))
    debug = os.getenv('FLASK_ENV') == 'development'

    print(f"Starting Multitenant RAG API on port {port}")
    print(f"Debug mode: {debug}")
    print(f"Available tenants: {', '.join(TENANT_CONFIG.keys())}")

    app.run(host='0.0.0.0', port=port, debug=debug)
