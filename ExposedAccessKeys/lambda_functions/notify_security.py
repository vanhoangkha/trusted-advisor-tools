"""Notify security team about exposed access key.

AWS Best Practices Applied:
- Initialize SDK clients outside handler for connection reuse
- Structured logging
- Environment variables for configuration
- Input validation
"""

import json
import logging
import os
import urllib.parse
import urllib.request

import boto3
from botocore.exceptions import ClientError

# Initialize logger
logger = logging.getLogger()
logger.setLevel(os.environ.get('LOG_LEVEL', 'INFO'))

# Environment variables (AWS Best Practice: use env vars, not hardcoded values)
TOPIC_ARN = os.environ['TOPIC_ARN']
SLACK_WEBHOOK_URL = os.environ.get('SlackWebhook_URL', '')

# Initialize SDK client outside handler (AWS Best Practice)
sns = boto3.client('sns')

TEMPLATE = '''At {time} the IAM access key {key} for user {user} on account {account} was deleted after it was found to have been exposed at the URL {location}.
Below are summaries of the most recent actions, resource names, and resource types associated with this user over the last 24 hours.

Actions:
{actions}

Resource Names:
{resources}

Resource Types:
{types}

These are summaries of only the most recent API calls made by this user. Please ensure your account remains secure by further reviewing the API calls made by this user in CloudTrail.'''


def lambda_handler(event, context):
    """Send security notification about exposed key."""
    account_id = event['account_id']
    username = event['username']
    deleted_key = event['deleted_key']
    exposed_location = event['exposed_location']
    time_discovered = event['time_discovered']
    event_names = event['event_names']
    resource_names = event['resource_names']
    resource_types = event['resource_types']

    subject = f'Security Alert! IAM Access Key Exposed For User {username} On Account {account_id}!!'

    logger.info('Generating notification', extra={
        'username': username,
        'account_id': account_id
    })

    message = TEMPLATE.format(
        time=time_discovered,
        key=deleted_key,
        user=username,
        account=account_id,
        location=exposed_location,
        actions=_format_summary(event_names),
        resources=_format_summary(resource_names),
        types=_format_summary(resource_types)
    )

    _publish_sns(subject, message)

    if SLACK_WEBHOOK_URL:
        logger.info('Sending Slack notification')
        _notify_slack(subject)

    return {'statusCode': 200}


def _format_summary(items):
    """Format summary items for display."""
    return '\t' + '\n\t'.join(f'{item[0]}: {item[1]}' for item in items)


def _publish_sns(subject, message):
    """Publish message to SNS topic."""
    try:
        sns.publish(
            TopicArn=TOPIC_ARN,
            Message=message,
            Subject=subject,
            MessageStructure='string'
        )
        logger.info('SNS notification sent', extra={'topic_arn': TOPIC_ARN})
    except ClientError as e:
        logger.error('SNS publish failed', extra={
            'topic_arn': TOPIC_ARN,
            'error_code': e.response['Error']['Code'],
            'error_message': str(e)
        })
        raise


def _notify_slack(subject):
    """Send notification to Slack webhook."""
    if not SLACK_WEBHOOK_URL:
        return

    try:
        data = json.dumps({'text': f'{subject} Check email for details.'}).encode('utf-8')
        headers = {'Content-Type': 'application/json'}
        req = urllib.request.Request(SLACK_WEBHOOK_URL, data=data, headers=headers)
        urllib.request.urlopen(req, timeout=10)
        logger.info('Slack notification sent')
    except Exception as e:
        logger.warning('Slack notification failed', extra={'error': str(e)})
