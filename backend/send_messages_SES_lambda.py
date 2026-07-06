import boto3
import json
import os
from botocore.exceptions import ClientError

# SES client (update region if needed)
ses = boto3.client('ses', region_name='us-east-1')

# Environment variables
FROM = os.environ['FROM']  # Must be verified in SES
TO = os.environ['TO']      # Your email, any recipient in production mode
# Optional: lock CORS to your domain instead of "*"
ALLOWED_ORIGIN = os.environ.get('ALLOWED_ORIGIN', '*')

# Basic abuse limits
MAX_NAME = 100
MAX_EMAIL = 254
MAX_MESSAGE = 5000


def _resp(status, payload):
    return {
        'statusCode': status,
        'headers': {
            'Content-Type': 'application/json',
            'Access-Control-Allow-Origin': ALLOWED_ORIGIN,
            'Access-Control-Allow-Headers': 'Content-Type',
            'Access-Control-Allow-Methods': 'POST, OPTIONS',
        },
        'body': json.dumps(payload),
    }


def lambda_handler(event, context):
    # Handle CORS preflight
    if (event.get('httpMethod') or '').upper() == 'OPTIONS':
        return _resp(200, {'message': 'ok'})

    try:
        body = json.loads(event.get('body') or '{}')

        # Honeypot: bots fill hidden fields. Pretend success, send nothing.
        if body.get('company') or body.get('website'):
            return _resp(200, {'message': 'Message sent successfully!'})

        name = (body.get('name') or '').strip()
        email = (body.get('email') or '').strip()
        message = (body.get('message') or '').strip()

        # Server-side validation (never trust the client)
        if not name or not email or not message:
            return _resp(400, {'error': 'Name, email and message are required.'})
        if '@' not in email or '.' not in email.split('@')[-1]:
            return _resp(400, {'error': 'Please provide a valid email address.'})
        if len(name) > MAX_NAME or len(email) > MAX_EMAIL or len(message) > MAX_MESSAGE:
            return _resp(400, {'error': 'One or more fields exceed the allowed length.'})

        subject = f"Portfolio Message from {name}"
        email_body = f"Name: {name}\nEmail: {email}\n\nMessage:\n{message}"

        ses.send_email(
            Source=FROM,
            Destination={'ToAddresses': [TO]},
            # Let visitors' address be the reply target without spoofing the sender
            ReplyToAddresses=[email] if '@' in email else [],
            Message={
                'Subject': {'Data': subject},
                'Body': {'Text': {'Data': email_body}},
            },
        )

        return _resp(200, {'message': 'Message sent successfully!'})

    except ClientError as e:
        print(f"SES Error: {e.response['Error']['Message']}")
        return _resp(500, {'error': 'Failed to send message via SES'})

    except Exception as e:
        print(f"Error: {str(e)}")
        return _resp(500, {'error': 'Internal server error'})
