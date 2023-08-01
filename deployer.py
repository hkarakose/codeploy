import boto3
import time
import zipfile
import os
import subprocess
import logging
from configparser import ConfigParser
import argparse
from datetime import datetime


# Configure logging
logging.basicConfig(level=logging.INFO, filename="codeploy.log")
logger = logging.getLogger(__name__)

# Function to execute the specified shell script
def execute_shell_script(script_path):
        logger.info(f"Executing shell script: {script_path}")
        result=subprocess.getoutput(script_path)
        logger.info(f"Shell script execution complete: {script_path}, {result}")


# Function to install the application
def install():
	execute_shell_script("chmod +x ./bundle/hooks/*.sh")

	# Execute ApplicationStop.sh
	execute_shell_script("./bundle/hooks/ApplicationStop.sh")

	# Execute BeforeInstall.sh
	execute_shell_script("./bundle/hooks/BeforeInstall.sh")

	# Copy contents of ./codedeploy/ to /home/ec2-user
	logger.info("Copying contents of ./bundle/ to /home/ec2-user")
	os.makedirs("/home/ec2-user", exist_ok=True)
	os.system("cp -R ./bundle/* /home/ec2-user/")

	# Execute AfterInstall.sh
	execute_shell_script("./bundle/hooks/AfterInstall.sh")

	# Execute ApplicationStart.sh
	execute_shell_script("./bundle/hooks/ApplicationStart.sh")

def arg_parser():
	parser = argparse.ArgumentParser(description="Deployer Script")
	parser.add_argument("--s3-bucket", help="S3 bucket name")
	parser.add_argument("--target-key-file", help="Target file key")
	parser.add_argument("--profile_name", help="Profile name")
	return parser.parse_args()


# Read the configuration file
config = ConfigParser()
config_file = "config.ini"
config.read(config_file)

# Retrieve the values from the configuration file
if config.has_section("Settings"):
	s3_bucket = config.get("Settings", "s3_bucket")
	target_file_key = config.get("Settings", "target_file_key")
	profile_name = config.get("Settings", "profile_name")

# Update the values if provided through command line arguments
args = arg_parser()
if args.s3_bucket:
	s3_bucket = args.s3_bucket
if args.target_key_file:
	target_file_key = args.target_key_file
if args.profile_name:
	profile_name = args.profile_name

# Update the configuration file if it doesn't exist
if not config.has_section("Settings"):
	config.add_section("Settings")
config.set("Settings", "s3_bucket", s3_bucket)
config.set("Settings", "target_file_key", target_file_key)
config.set("Settings", "profile_name", profile_name)
with open(config_file, "w") as f:
	config.write(f)

# Create an AWS session with the specified profile
session = boto3.Session(profile_name=profile_name)

# Create an S3 client using the session
s3_client = session.client("s3")

# Construct the S3 file URIs
target_file_uri = f"s3://{s3_bucket}/{target_file_key}"


# Function to check if the LATEST_VERSION file has changed
def has_version_changed(bucket_name, file_name):
	logger.info(f"Checking bucket: {bucket_name}, file: {file_name}")

	last_modified = s3_client.head_object(Bucket=bucket_name, Key=file_name)["LastModified"]
	logger.info(f"Last modified time: {last_modified}")

	if not config.has_option("Settings", "last_fetch_time"):
		last_fetch_time = "1970-01-01 00:00:00+00:00"
	else:
		last_fetch_time = config.get("Settings", "last_fetch_time")

	# Convert the string to a datetime object
	last_fetch_time_obj = datetime.strptime(last_fetch_time, "%Y-%m-%d %H:%M:%S%z")
	logger.info(f"Last fetch time: {last_fetch_time_obj}")

	# Compare the last modified time of the file to the current time.
	if last_fetch_time_obj < last_modified:
		last_fetch_time = last_modified
		logger.info("Updating last_fetch_time")
		config.set("Settings", "last_fetch_time", last_fetch_time.strftime("%Y-%m-%d %H:%M:%S%z"))
		with open(config_file, "w") as f:
			config.write(f)
		return True
	else:
		return False


# Function to download the target file
def download_file():
	logger.info(f"Downloading file: {target_file_uri}")
	s3_client.download_file(s3_bucket, target_file_key, target_file_key)
	logger.info(f"Download complete: {target_file_key}")


# Function to unzip the downloaded file
def unzip_file():
	logger.info(f"Unzipping file: {target_file_key}")
	with zipfile.ZipFile(target_file_key, "r") as zip_ref:
		zip_ref.extractall("./bundle")
	logger.info("Unzip complete")


while True:
	version_changed = has_version_changed(bucket_name=s3_bucket, file_name=target_file_key)

	if version_changed:
		logger.info("Version has changed. Downloading new file...")
		download_file()

		logger.info("Unzipping downloaded file...")
		unzip_file()

		install()
	else:
		logger.info("Version not changed")

	logger.info("Sleep for 60 seconds before polling again")
	time.sleep(60)
