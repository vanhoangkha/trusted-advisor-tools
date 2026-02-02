"""Remove idle RDS databases based on Trusted Advisor check.

AWS Best Practices Applied:
- Initialize SDK clients outside handler where possible
- Structured logging
- Environment variables for configuration
- Input validation
- Idempotent design (checks thresholds before action)
- SNS notification for audit trail
"""

import json
import logging
import os

import boto3
from botocore.exceptions import ClientError

# Initialize logger
logger = logging.getLogger()
logger.setLevel(os.environ.get('LOG_LEVEL', 'INFO'))

# Configuration via environment variables (AWS Best Practice)
MIN_AGE = int(os.environ.get('MIN_AGE', '14'))
TERMINATION_METHOD = os.environ.get('TERMINATION_METHOD', 'stop')
SNS_TOPIC_ARN = os.environ.get('SNS_TOPIC_ARN', '')
ACCOUNT_ID = os.environ.get('ACCOUNT_ID', '')

# Initialize SNS client outside handler
sns = boto3.client('sns') if SNS_TOPIC_ARN else None


def lambda_handler(event, context):
    """Handle Trusted Advisor idle RDS check event."""
    # Input validation
    if 'detail' not in event or 'check-item-detail' not in event.get('detail', {}):
        logger.error('Invalid event structure')
        raise ValueError('Invalid Trusted Advisor event structure')

    details = event['detail']['check-item-detail']
    region = details.get('Region')
    db_instance_name = details.get('DB Instance Name')
    days_since_connection = details.get('Days Since Last Connection', '0')

    # Parse days (handle "14+" format)
    last_connection = int(str(days_since_connection).strip('+'))

    logger.info('Processing idle RDS instance', extra={
        'db_instance': db_instance_name,
        'region': region,
        'days_idle': last_connection,
        'min_age_threshold': MIN_AGE
    })

    # Idempotent check - only act if threshold exceeded
    if last_connection < MIN_AGE:
        logger.info('Instance does not meet minimum threshold', extra={
            'db_instance': db_instance_name,
            'days_idle': last_connection,
            'threshold': MIN_AGE
        })
        return {'statusCode': 200, 'body': 'Below threshold, no action taken'}

    # Initialize RDS client for specific region
    rds = boto3.client('rds', region_name=region)

    if TERMINATION_METHOD == 'delete':
        return _delete_db_instance(db_instance_name, rds)
    return _stop_db_instance(db_instance_name, rds)


def _send_notification(message):
    """Send SNS notification."""
    if not SNS_TOPIC_ARN or not sns:
        logger.info('SNS topic not configured, skipping notification')
        return

    try:
        sns.publish(
            TopicArn=SNS_TOPIC_ARN,
            Subject=f'RDS Idle Database Termination Notification ({ACCOUNT_ID})',
            Message=message,
            MessageStructure='string',
        )
        logger.info('SNS notification sent')
    except ClientError as e:
        logger.warning('Failed to send SNS notification', extra={
            'error_code': e.response['Error']['Code']
        })


def _delete_db_instance(db_instance_name, rds):
    """Delete RDS instance with final snapshot."""
    final_snapshot_id = f'{db_instance_name}-final-snapshot'
    try:
        rds.delete_db_instance(
            DBInstanceIdentifier=db_instance_name,
            FinalDBSnapshotIdentifier=final_snapshot_id,
        )
        logger.info('Database instance deleted', extra={'db_instance': db_instance_name, 'final_snapshot': final_snapshot_id})
        _send_notification(f'Database instance {db_instance_name} has been deleted.\nFinal snapshot: {final_snapshot_id}')
        return {'statusCode': 200, 'body': json.dumps({'message': 'Database instance deleted'})}
    except ClientError as e:
        error_code = e.response['Error']['Code']
        if error_code == 'DBInstanceNotFound':
            logger.warning('DB instance not found', extra={'db_instance': db_instance_name})
            return {'statusCode': 200, 'body': json.dumps({'message': f'DB instance {db_instance_name} not found'})}
        logger.error('Failed to delete database instance', extra={'db_instance': db_instance_name, 'error_code': error_code})
        raise


def _stop_db_instance(db_instance_name, rds):
    """Stop RDS instance."""
    try:
        rds.stop_db_instance(DBInstanceIdentifier=db_instance_name)
        logger.info('Database instance stopped', extra={'db_instance': db_instance_name})
        _send_notification(f'Database instance {db_instance_name} has been stopped.')
        return {'statusCode': 200, 'body': json.dumps({'message': 'Database instance stopped'})}
    except ClientError as e:
        error_code = e.response['Error']['Code']
        if error_code == 'DBInstanceNotFound':
            logger.warning('DB instance not found', extra={'db_instance': db_instance_name})
            return {'statusCode': 200, 'body': json.dumps({'message': f'DB instance {db_instance_name} not found'})}
        if error_code == 'InvalidDBInstanceState':
            logger.info('DB instance already stopped', extra={'db_instance': db_instance_name})
            return {'statusCode': 200, 'body': json.dumps({'message': f'DB instance {db_instance_name} already stopped'})}
        logger.error('Failed to stop database instance', extra={'db_instance': db_instance_name, 'error_code': error_code})
        raise
