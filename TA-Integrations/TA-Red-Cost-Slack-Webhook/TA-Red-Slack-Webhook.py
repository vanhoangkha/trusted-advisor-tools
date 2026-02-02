"""Slack webhook for Trusted Advisor cost alerts.

AWS Best Practices Applied:
- No sensitive data in logs
- Structured logging
- Input validation
- Timeout on HTTP requests
"""

import json
import logging
import os
import urllib.parse
import urllib.request

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger()
logger.setLevel(os.environ.get('LOG_LEVEL', 'INFO'))

# Initialize client outside handler
support = boto3.client('support', region_name='us-east-1')


def lambda_handler(event, context):
    """Send Trusted Advisor summary to Slack."""
    # Input validation
    slack_webhook_url = event.get('SlackWebhookURL', '')
    if not slack_webhook_url or slack_webhook_url.startswith('<'):
        logger.error('Invalid or missing Slack webhook URL')
        return {'statusCode': 400, 'body': 'Invalid webhook URL'}

    # Validate URL format (must be HTTPS)
    if not slack_webhook_url.startswith('https://'):
        logger.error('Webhook URL must use HTTPS')
        return {'statusCode': 400, 'body': 'Webhook URL must use HTTPS'}

    logger.info('Fetching Trusted Advisor checks')  # Don't log the URL!

    try:
        response = support.describe_trusted_advisor_checks(language='en')
    except ClientError as e:
        logger.error('Failed to get TA checks', extra={'error_code': e.response['Error']['Code']})
        raise

    checks = response['checks']
    check_ids = [c['id'] for c in checks]
    ta_checks_dict = {c['id']: {'name': c['name'], 'category': c['category']} for c in checks}

    result = support.describe_trusted_advisor_check_summaries(checkIds=check_ids)

    # Analyze results
    stats = _analyze_checks(result['summaries'], ta_checks_dict)

    # Build message
    message = _build_message(stats)

    # Send to Slack
    _send_to_slack(slack_webhook_url, message)

    return {'statusCode': 200}


def _analyze_checks(summaries, ta_checks_dict):
    """Analyze check summaries and return statistics."""
    stats = {
        'critical': 0,
        'warnings': 0,
        'ok': 0,
        'categories': {
            'security': 0,
            'fault_tolerance': 0,
            'performance': 0,
            'cost_optimizing': 0,
            'service_limits': 0
        },
        'critical_checks': [],
        'estimated_savings': 0.0
    }

    for summary in summaries:
        status = summary['status']
        check_id = summary['checkId']

        if status == 'ok':
            stats['ok'] += 1
        elif status == 'warning':
            stats['warnings'] += 1
        elif status == 'error':
            stats['critical'] += 1
            check_info = ta_checks_dict.get(check_id, {})
            category = check_info.get('category', 'unknown')
            stats['categories'][category] = stats['categories'].get(category, 0) + 1
            stats['critical_checks'].append(f"[{category}] {check_info.get('name', 'Unknown')}")

        # Sum estimated savings
        try:
            savings = summary.get('categorySpecificSummary', {}).get('costOptimizing', {}).get('estimatedMonthlySavings', 0)
            stats['estimated_savings'] += savings
        except (KeyError, TypeError):
            pass

    return stats


def _build_message(stats):
    """Build Slack message from statistics."""
    lines = [
        '=== Trusted Advisor Summary ===',
        '',
        f"🔴 Critical: {stats['critical']}",
        f"🟡 Warnings: {stats['warnings']}",
        f"🟢 OK: {stats['ok']}",
        '',
        f"💰 Estimated Monthly Savings: ${stats['estimated_savings']:.2f}",
        ''
    ]

    if stats['critical_checks']:
        lines.append('Critical Findings:')
        for check in stats['critical_checks'][:10]:  # Limit to 10
            lines.append(f"  • {check}")

    return '\n'.join(lines)


def _send_to_slack(webhook_url, message):
    """Send message to Slack webhook."""
    try:
        data = json.dumps({'text': message}).encode('utf-8')
        headers = {'Content-Type': 'application/json'}
        req = urllib.request.Request(webhook_url, data=data, headers=headers)
        urllib.request.urlopen(req, timeout=10)
        logger.info('Slack notification sent successfully')
    except Exception as e:
        # Don't log the URL or full error (could contain sensitive info)
        logger.error('Failed to send Slack notification')
        raise
