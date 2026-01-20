import argparse
import json
import sys

import boto3


def create_ssm_parameters(
    json_file: str,
    prefix: str = "/fake_tenant_id_123/api-key/",
    region: str = "us-east-1",
    dry_run: bool = False,
) -> None:
    try:
        with open(json_file) as f:
            data = json.load(f)
    except FileNotFoundError:
        print(f"Error: File '{json_file}' not found")
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON in file '{json_file}': {e}")
        sys.exit(1)

    if not isinstance(data, list):
        sys.exit(1)

    ssm_client = boto3.client("ssm", region_name=region)

    created_params = []
    failed_params = []

    for item in data:
        if not isinstance(item, dict) or "key" not in item or "value" not in item:
            print(f"Warning: Skipping invalid item (must have 'key' and 'value' fields): {item}")
            continue

        key = item["key"]
        value = item["value"]

        param_name = f"{prefix}{key}"

        param_value = str(value) if not isinstance(value, str) else value

        if dry_run:
            print(f"[DRY RUN] Would create parameter: {param_name}")
            print(f"  Value: {param_value[:50]}{'...' if len(param_value) > 50 else ''}")
        else:
            try:
                ssm_client.put_parameter(
                    Name=param_name,
                    Value=param_value,
                    Type="SecureString",
                    Tier="Advanced",
                    Overwrite=True,
                    Description=f"Created from {json_file}",
                )
                created_params.append(param_name)
                print(f"✓ Created parameter: {param_name}")
            except Exception as e:
                failed_params.append((param_name, str(e)))
                print(f"✗ Failed to create parameter: {param_name}")
                print(f"  Error: {e}")

    print("\n" + "=" * 50)
    if dry_run:
        print("DRY RUN COMPLETE - No parameters were actually created")
    else:
        print("Summary:")
        print(f"  Successfully created: {len(created_params)} parameters")
        print(f"  Failed: {len(failed_params)} parameters")

        if created_params:
            print("\nCreated parameters:")
            for param in created_params:
                print(f"  - {param}")

        if failed_params:
            print("\nFailed parameters:")
            for param, error in failed_params:
                print(f"  - {param}: {error}")


def main():
    parser = argparse.ArgumentParser(
        description="Create AWS SSM SecureString parameters from a JSON file"
    )
    parser.add_argument("json_file", help="Path to JSON file containing array of key-value objects")
    parser.add_argument(
        "--prefix",
        default="/fake_tenant_id_123/api-key/",
        help="Prefix for SSM parameter names (default: /fake_tenant_id_123/api-key/)",
    )
    parser.add_argument("--region", default="us-east-1", help="AWS region (default: us-east-1)")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be created without actually creating parameters",
    )

    args = parser.parse_args()

    # Ensure prefix ends with /
    if not args.prefix.endswith("/"):
        args.prefix += "/"

    print(f"Creating SSM parameters from: {args.json_file}")
    print(f"Using prefix: {args.prefix}")
    print(f"AWS Region: {args.region}")
    if args.dry_run:
        print("Mode: DRY RUN (no actual changes will be made)")
    print("=" * 50 + "\n")

    create_ssm_parameters(
        args.json_file, prefix=args.prefix, region=args.region, dry_run=args.dry_run
    )


if __name__ == "__main__":
    main()
