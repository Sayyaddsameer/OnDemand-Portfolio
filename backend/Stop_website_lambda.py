import boto3, os, json
from botocore.exceptions import ClientError

s3 = boto3.client('s3')
BUCKET = os.environ.get('BUCKET')


def lambda_handler(event, context):
    try:
        s3.delete_bucket_policy(Bucket=BUCKET)
        print(f"Public read policy removed from {BUCKET}; website is now private.")
    except ClientError as e:
        code = e.response['Error']['Code']
        # Already private / no policy present is fine and idempotent.
        if code in ('NoSuchBucketPolicy', 'NoSuchBucket'):
            print(f"No policy to remove ({code}); bucket already private.")
        else:
            # Anything else must surface so a stuck-public bucket is visible.
            print(f"Failed to remove bucket policy: {code}")
            raise
    return {"statusCode": 200, "body": json.dumps({"message": "Website stopped"})}
