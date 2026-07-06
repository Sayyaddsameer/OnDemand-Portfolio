import boto3, json, os, uuid
from datetime import datetime, timedelta, timezone

sns = boto3.client('sns')
s3 = boto3.client('s3')
scheduler = boto3.client('scheduler')

BUCKET = os.environ['BUCKET']
SITE_URL = os.environ['SITE_URL']
STOP_LAMBDA_ARN = os.environ['STOP_LAMBDA_ARN']
SCHEDULER_ROLE_ARN = os.environ['SCHEDULER_ROLE_ARN']
# Move the hardcoded ARN out of source. Optional: leave unset to skip notifications.
SNS_TOPIC_ARN = os.environ.get('SNS_TOPIC_ARN')

# A single, fixed schedule name so concurrent visitors don't create a pile-up
# of one-off schedules and don't cut each other's session short. Each visit
# pushes the single "stop" time out to now + 30 min instead.
SCHEDULE_NAME = "stop-portfolio-website"


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

    # (Re)schedule the single stop for 30 min from now. Create if missing,
    # otherwise update the existing one so the newest visitor extends the window.
    run_time = datetime.now(timezone.utc) + timedelta(minutes=30)
    params = dict(
        Name=SCHEDULE_NAME,
        ScheduleExpression=f"at({run_time.strftime('%Y-%m-%dT%H:%M:%S')})",
        FlexibleTimeWindow={'Mode': 'OFF'},
        Target={'Arn': STOP_LAMBDA_ARN, 'RoleArn': SCHEDULER_ROLE_ARN},
    )
    try:
        scheduler.create_schedule(**params)
    except scheduler.exceptions.ConflictException:
        scheduler.update_schedule(**params)

    # Notification is best-effort: never let it break the redirect.
    if SNS_TOPIC_ARN:
        try:
            sns.publish(
                TopicArn=SNS_TOPIC_ARN,
                Message='Someone just started your portfolio website!',
                Subject='Portfolio Notification'
            )
        except Exception as e:
            print(f"SNS publish failed (non-fatal): {e}")

    # redirect
    return {
        "statusCode": 302,
        "headers": {"Location": SITE_URL},
        "body": json.dumps({"message": "Redirecting"})
    }
