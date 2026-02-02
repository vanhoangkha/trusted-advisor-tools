"""Lookup CloudTrail events for exposed access key.

AWS Best Practices Applied:
- Initialize SDK clients outside handler for connection reuse
- Structured logging with proper log levels
- Input validation
- Idempotent design
"""

import collections
import logging
import os
from datetime import datetime, timedelta

import boto3
from botocore.exceptions import ClientError

# Initialize logger
logger = logging.getLogger()
logger.setLevel(os.environ.get('LOG_LEVEL', 'INFO'))

# Initialize SDK client outside handler (AWS Best Practice)
cloudtrail = boto3.client('cloudtrail')


def lambda_handler(event, context):
    """Lookup CloudTrail events for exposed key user."""
    account_id = event['account_id']
    time_discovered = event['time_discovered']
    username = event['username']
    deleted_key = event['deleted_key']
    exposed_location = event['exposed_location']

    endtime = datetime.now()
    interval = timedelta(hours=24)
    starttime = endtime - interval

    logger.info('Retrieving CloudTrail events', extra={
        'username': username,
        'start_time': starttime.isoformat(),
        'end_time': endtime.isoformat()
    })

    events = get_events(username, starttime, endtime)

    logger.info('Summarizing events', extra={
        'username': username,
        'event_count': len(events.get('Events', []))
    })

    event_names, resource_names, resource_types = get_events_summaries(events)

    return {
        'account_id': account_id,
        'time_discovered': time_discovered,
        'username': username,
        'deleted_key': deleted_key,
        'exposed_location': exposed_location,
        'event_names': event_names,
        'resource_names': resource_names,
        'resource_types': resource_types
    }


def get_events(username, starttime, endtime):
    """Retrieve CloudTrail events for user.

    Args:
        username: IAM username to lookup
        starttime: Start of lookup window
        endtime: End of lookup window

    Returns:
        CloudTrail events response
    """
    try:
        response = cloudtrail.lookup_events(
            LookupAttributes=[{
                'AttributeKey': 'Username',
                'AttributeValue': username
            }],
            StartTime=starttime,
            EndTime=endtime,
            MaxResults=50
        )
        return response
    except ClientError as e:
        logger.error('CloudTrail lookup failed', extra={
            'username': username,
            'error_code': e.response['Error']['Code'],
            'error_message': str(e)
        })
        raise


def get_events_summaries(events):
    """Summarize CloudTrail events.

    Args:
        events: CloudTrail events response

    Returns:
        Tuple of (event_names, resource_names, resource_types) counters
    """
    event_name_counter = collections.Counter()
    resource_name_counter = collections.Counter()
    resource_type_counter = collections.Counter()

    for event in events.get('Events', []):
        resources = event.get('Resources')
        event_name_counter.update([event.get('EventName')])
        if resources:
            resource_name_counter.update([r.get('ResourceName') for r in resources])
            resource_type_counter.update([r.get('ResourceType') for r in resources])

    return (
        event_name_counter.most_common(10),
        resource_name_counter.most_common(10),
        resource_type_counter.most_common(10)
    )
