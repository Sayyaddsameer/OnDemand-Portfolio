import boto3, os, json
s3 = boto3.client('s3')
BUCKET = os.environ.get('BUCKET')

def lambda_handler(event, context):
    try:
        s3.delete_bucket_policy(Bucket=BUCKET)
    except:
        pass
    return {"statusCode":200,"body":json.dumps({"message":"Website stopped"})}
