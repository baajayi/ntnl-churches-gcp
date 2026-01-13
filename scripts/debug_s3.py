#!/usr/bin/env python3
"""
S3 Diagnostic Script - Lists all objects in a bucket with optional prefix
Helps debug S3 access and path issues
"""

import sys
import argparse

try:
    import boto3
    from botocore.exceptions import ClientError, NoCredentialsError
except ImportError:
    print("Error: boto3 not installed. Run: pip install boto3")
    sys.exit(1)


def list_all_objects(bucket, prefix="", max_keys=100):
    """List objects in S3 bucket with detailed information"""
    try:
        s3_client = boto3.client('s3')

        print(f"Connecting to S3 bucket: {bucket}")
        print(f"Prefix: '{prefix}' (empty string means root)")
        print("=" * 80)

        # First, try to list with the exact prefix
        paginator = s3_client.get_paginator('list_objects_v2')

        objects = []
        total_size = 0

        try:
            for page in paginator.paginate(Bucket=bucket, Prefix=prefix, MaxKeys=max_keys):
                for obj in page.get('Contents', []):
                    objects.append(obj)
                    total_size += obj.get('Size', 0)
        except ClientError as e:
            error_code = e.response['Error']['Code']
            if error_code == 'NoSuchBucket':
                print(f"Error: Bucket '{bucket}' does not exist or you don't have access to it.")
                return
            elif error_code == 'AccessDenied':
                print(f"Error: Access denied to bucket '{bucket}'. Check your AWS credentials and permissions.")
                return
            else:
                print(f"Error listing objects: {e}")
                return

        if not objects:
            print(f"\nNo objects found with prefix '{prefix}'")
            print("\nTrying to list root level objects to help diagnose...")
            print("-" * 80)

            # Try listing root level
            try:
                root_page = s3_client.list_objects_v2(Bucket=bucket, Delimiter='/', MaxKeys=50)

                # List common prefixes (folders)
                common_prefixes = root_page.get('CommonPrefixes', [])
                if common_prefixes:
                    print("\nTop-level folders found:")
                    for cp in common_prefixes:
                        print(f"  📁 {cp['Prefix']}")

                # List files in root
                root_objects = root_page.get('Contents', [])
                if root_objects:
                    print("\nFiles in root:")
                    for obj in root_objects[:20]:
                        size_kb = obj['Size'] / 1024
                        print(f"  📄 {obj['Key']} ({size_kb:.2f} KB)")

                if not common_prefixes and not root_objects:
                    print("  (Bucket appears to be empty)")

            except Exception as e:
                print(f"Error listing root: {e}")

            print("\n" + "=" * 80)
            print("TIPS:")
            print("  1. Check if the prefix matches exactly (S3 is case-sensitive)")
            print("  2. Try without trailing slash, or with trailing slash")
            print("  3. Use one of the folders listed above")
            print(f"     Example: --s3-prefix 'FolderName/'")
            return

        # Display found objects
        print(f"\n✓ Found {len(objects)} objects")
        print(f"Total size: {total_size / (1024*1024):.2f} MB")
        print("\nObjects:")
        print("-" * 80)

        for obj in objects[:50]:  # Show first 50
            key = obj['Key']
            size = obj['Size']
            last_modified = obj['LastModified']

            # Determine file extension
            ext = key.split('.')[-1].lower() if '.' in key else 'none'
            size_display = f"{size / 1024:.2f} KB" if size < 1024*1024 else f"{size / (1024*1024):.2f} MB"

            print(f"  {key}")
            print(f"    Size: {size_display}, Modified: {last_modified}, Extension: .{ext}")

        if len(objects) > 50:
            print(f"\n  ... and {len(objects) - 50} more objects")

        # Summary by extension
        print("\n" + "=" * 80)
        print("File types found:")
        extensions = {}
        for obj in objects:
            key = obj['Key']
            if not key.endswith('/'):  # Skip folder markers
                ext = '.' + key.split('.')[-1].lower() if '.' in key else 'no-extension'
                extensions[ext] = extensions.get(ext, 0) + 1

        for ext, count in sorted(extensions.items(), key=lambda x: x[1], reverse=True):
            print(f"  {ext}: {count} files")

    except NoCredentialsError:
        print("Error: AWS credentials not found.")
        print("Configure via:")
        print("  - Environment variables (AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY)")
        print("  - ~/.aws/credentials file")
        print("  - IAM role (if running on EC2)")
    except Exception as e:
        print(f"Unexpected error: {e}")
        import traceback
        traceback.print_exc()


def main():
    parser = argparse.ArgumentParser(
        description='Debug S3 bucket access and list objects',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # List all objects in bucket
  python scripts/debug_s3.py --bucket my-bucket

  # List objects with specific prefix
  python scripts/debug_s3.py --bucket my-bucket --prefix "documents/"

  # List with different prefix variations
  python scripts/debug_s3.py --bucket my-bucket --prefix "Luther Commentary/"
  python scripts/debug_s3.py --bucket my-bucket --prefix "Luther Commentary"
        """
    )

    parser.add_argument('--bucket', required=True, help='S3 bucket name')
    parser.add_argument('--prefix', default='', help='S3 prefix/path (try with and without trailing slash)')
    parser.add_argument('--max-keys', type=int, default=1000, help='Maximum number of keys to retrieve')

    args = parser.parse_args()

    list_all_objects(args.bucket, args.prefix, args.max_keys)


if __name__ == '__main__':
    main()
