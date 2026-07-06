import boto3
import json
import os
from botocore.exceptions import ClientError

# SES client (update region if needed)
ses = boto3.client('ses', region_name='us-east-1')

# Environment variables
FROM = os.environ['FROM']  # Must be verified in SES
TO = os.environ['TO']      # Your email, any recipient in production mode

def lambda_handler(event, context):
    try:
        # Parse the incoming POST body
        body = json.loads(event.get('body', '{}'))
        name = body.get('name', 'Anonymous')
        email = body.get('email', 'No Email')
        message = body.get('message', 'No Message')

        # Compose email content
        subject = f"Portfolio Message from {name}"
        email_body = f"Name: {name}\nEmail: {email}\n\nMessage:\n{message}"

        # Send email via SES
        response = ses.send_email(
            Source=FROM,
            Destination={'ToAddresses':[TO]},
            Message={
                'Subject': {'Data': subject},
                'Body': {'Text': {'Data': email_body}}
            }
        )

        # Success response
        return {
            'statusCode': 200,
            'body': json.dumps({'message': 'Message sent successfully!'})
        }

    except ClientError as e:
        # SES error
        print(f"SES Error: {e.response['Error']['Message']}")
        return {
            'statusCode': 500,
            'body': json.dumps({
                'error': 'Failed to send message via SES',
                'details': e.response['Error']['Message']
            })
        }

    except Exception as e:
        # General error
        print(f"Error: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps({'error': 'Internal server error', 'details': str(e)})
        }
