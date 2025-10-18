# Summary 
Checks an s3 bucket for new version.

If found, 
 - downloads it, 
 - extracts the bundle
 - installs it.

# Long Description

## Overview
`deployer.py` is an **automated deployment agent** that continuously monitors an S3 bucket for new application versions and automatically deploys them when changes are detected.

## Key Functionality

### 1. **Continuous Monitoring**
- Runs in an infinite loop, checking every 60 seconds
- Monitors a specific file in an S3 bucket for changes by comparing the file's `LastModified` timestamp
- Tracks the last fetch time in a configuration file to detect new versions

### 2. **Configuration Management**
- Supports multiple deployment configurations in `config.ini` file
- Each configuration section contains S3 bucket, file key, and AWS profile settings
- Accepts command-line arguments to specify which configuration to use and override values
- Automatically updates the configuration file with new values
- Provides `--list-configs` option to view all available configurations

### 3. **Automated Deployment Process**
When a new version is detected, it:
1. **Downloads** the new deployment package (ZIP file) from S3
2. **Extracts** the ZIP file to a `./bundle` directory
3. **Executes deployment hooks** in sequence:
   - `ApplicationStop.sh` - Stops the current application
   - `BeforeInstall.sh` - Pre-installation tasks
   - Copies bundle contents to the target destination (from `appspec.yml`)
   - `AfterInstall.sh` - Post-installation tasks
   - `ApplicationStart.sh` - Starts the new application

### 4. **AWS CodeDeploy Integration**
- Uses `appspec.yml` file to determine deployment destination
- Follows AWS CodeDeploy lifecycle hooks pattern
- Integrates with AWS S3 using boto3 with configurable AWS profiles

### 5. **Safety Features**
- **Installation locking**: Prevents concurrent deployments using an `installation_in_progress` flag
- **Timeout protection**: Fails if installation takes more than 10 minutes
- **Comprehensive logging**: Logs all activities to `codeploy.log`

### 6. **Error Handling**
- Validates that destination exists in `appspec.yml`
- Handles AWS authentication through profiles
- Logs errors and execution results

## Usage

### Basic Usage
```bash
# Run with default configuration (Settings section)
python deployer.py

# Run with a specific configuration section
python deployer.py --config-section Production

# List all available configurations
python deployer.py --list-configs

# Override specific values for a configuration
python deployer.py --config-section Staging --s3-bucket my-custom-bucket --profile_name my-profile
```

### Configuration File Structure
The `config.ini` file supports multiple deployment environments:

```ini
[Settings]
s3_bucket = codedeploy-202107
target_file_key = business-services-test.zip
profile_name = 1tiklahost
last_fetch_time = 2023-07-30 19:41:09+0000
installation_in_progress = false

[Production]
s3_bucket = codedeploy-prod-202107
target_file_key = business-services-prod.zip
profile_name = production-profile
last_fetch_time = 1970-01-01 00:00:00+0000
installation_in_progress = false

[Staging]
s3_bucket = codedeploy-staging-202107
target_file_key = business-services-staging.zip
profile_name = staging-profile
last_fetch_time = 1970-01-01 00:00:00+0000
installation_in_progress = false
```

### Command Line Arguments
- `--config-section`: Specify which configuration section to use (default: Settings)
- `--list-configs`: List all available configuration sections
- `--s3-bucket`: Override the S3 bucket name
- `--target-key-file`: Override the target file key
- `--profile_name`: Override the AWS profile name

## Use Case
This script is designed for **continuous deployment scenarios** where you want applications to automatically update when new versions are pushed to an S3 bucket, similar to how AWS CodeDeploy works but as a lightweight, self-contained solution.

The script essentially creates a polling-based deployment agent that can run as a service (notice the `deployer.service` file in the directory) to keep applications automatically updated.

The multi-configuration support allows you to manage deployments for different environments (development, staging, production) from a single script and configuration file.
