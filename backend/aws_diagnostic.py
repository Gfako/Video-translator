import boto3
import os
from dotenv import load_dotenv
from botocore.exceptions import ClientError, NoCredentialsError

# Load environment variables
load_dotenv()

print("=== AWS S3 DIAGNOSTIC ===")
print(f"Access Key ID: {os.getenv('AWS_ACCESS_KEY_ID')}")
print(f"Region: {os.getenv('AWS_DEFAULT_REGION')}")
print(f"Target Bucket: uploadsbucket1")
print("=" * 40)

try:
    # Create S3 client
    s3_client = boto3.client(
        's3',
        aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
        aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY'),
        region_name=os.getenv('AWS_DEFAULT_REGION', 'eu-north-1')
    )
    
    print("✅ AWS credentials loaded successfully")
    
    # Test 1: List all buckets
    print("\n1. Checking if we can list buckets...")
    try:
        response = s3_client.list_buckets()
        print(f"✅ Found {len(response['Buckets'])} buckets:")
        for bucket in response['Buckets']:
            print(f"   - {bucket['Name']} (created: {bucket['CreationDate']})")
        
        # Check if our target bucket exists
        bucket_names = [bucket['Name'] for bucket in response['Buckets']]
        if 'uploadsbucket1' in bucket_names:
            print("✅ Target bucket 'uploadsbucket1' exists!")
        else:
            print("❌ Target bucket 'uploadsbucket1' NOT FOUND")
            print("   We need to create it or use a different name")
            
    except ClientError as e:
        error_code = e.response['Error']['Code']
        print(f"❌ Cannot list buckets: {error_code}")
        print(f"   Error message: {e.response['Error']['Message']}")
        print("   This usually means insufficient permissions")
    
    # Test 2: Check specific bucket access
    print("\n2. Checking access to 'uploadsbucket1'...")
    try:
        s3_client.head_bucket(Bucket='uploadsbucket1')
        print("✅ Can access 'uploadsbucket1'")
        
        # Check bucket location
        location = s3_client.get_bucket_location(Bucket='uploadsbucket1')
        bucket_region = location['LocationConstraint'] or 'us-east-1'
        print(f"✅ Bucket region: {bucket_region}")
        
        if bucket_region != os.getenv('AWS_DEFAULT_REGION'):
            print(f"⚠️  WARNING: Bucket is in {bucket_region} but your config uses {os.getenv('AWS_DEFAULT_REGION')}")
            
    except ClientError as e:
        error_code = e.response['Error']['Code']
        if error_code == 'NoSuchBucket':
            print("❌ Bucket 'uploadsbucket1' does not exist")
        elif error_code == 'Forbidden':
            print("❌ Access denied to bucket 'uploadsbucket1'")
        else:
            print(f"❌ Error accessing bucket: {error_code}")
            print(f"   Message: {e.response['Error']['Message']}")

except NoCredentialsError:
    print("❌ AWS credentials not found or invalid")
    print("   Check your .env file")
except Exception as e:
    print(f"❌ Unexpected error: {e}")

print("\n=== NEXT STEPS ===")
print("If bucket doesn't exist, we'll create it automatically")
print("If permissions issue, check IAM user permissions")
print("=" * 40)