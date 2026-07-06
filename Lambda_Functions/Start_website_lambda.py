import boto3, json, os, uuid
from datetime import datetime, timedelta, timezone

sns = boto3.client('sns')
s3 = boto3.client('s3')
scheduler = boto3.client('scheduler')

BUCKET = os.environ['BUCKET']
SITE_URL = os.environ['SITE_URL']
STOP_LAMBDA_ARN = os.environ['STOP_LAMBDA_ARN']
SCHEDULER_ROLE_ARN = os.environ['SCHEDULER_ROLE_ARN']

def lambda_handler(event, context):
    # make site public
    policy = {
        "Version": "2012-10-17",
        "Statement": [{
            "Sid": "PublicReadGetObject",
            "Effect": "Allow",
            "Principal": "*",
            "Action": ["s3:GetObject"],
            "Resource": [f"arn:aws:s3:::{BUCKET}/*"]
        }]
    }
    s3.put_bucket_policy(Bucket=BUCKET, Policy=json.dumps(policy))

    # schedule stop in 30 min
    run_time = datetime.now(timezone.utc) + timedelta(minutes=30)
    schedule_name = f"stop-website-{uuid.uuid4().hex[:8]}"
    scheduler.create_schedule(
        Name=schedule_name,
        ScheduleExpression=f"at({run_time.strftime('%Y-%m-%dT%H:%M:%S')})",
        FlexibleTimeWindow={'Mode':'OFF'},
        Target={
            'Arn': STOP_LAMBDA_ARN,
            'RoleArn': SCHEDULER_ROLE_ARN
        }
    )

    sns.publish(
    TopicArn='arn:aws:sns:us-east-1:785269092008:PortfolioSiteStarted',
    Message='Someone just started your portfolio website!',
    Subject='Portfolio Notification'
)

    # redirect
    return {
        "statusCode":302,
        "headers":{"Location":SITE_URL},
        "body":json.dumps({"message":"Redirecting"})
    }
