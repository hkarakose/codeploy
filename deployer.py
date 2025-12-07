import boto3
import time
import yaml
import zipfile
import os
import subprocess
import logging
from configparser import ConfigParser
import argparse
from datetime import datetime
import threading

# Configure logging with timestamp and log level
logging.basicConfig(level=logging.INFO, filename="codeploy.log", format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Function to execute the specified shell script
def execute_shell_script(script_path):
        logger.info(f"Executing shell script: {script_path}")
        result=subprocess.getoutput(script_path)
        logger.info(f"Shell script execution complete: {script_path}, {result}")

# Function to parse appspec.yml and extract destination
def get_destination_from_appspec(appspec_path):
	logger.info("Get destination")

	with open(appspec_path, 'r') as f:
		appspec_content = yaml.safe_load(f)

	# Assuming there's only one destination, fetching the first one
	files_section = appspec_content.get('files', [])
	if files_section and 'destination' in files_section[0]:
		return files_section[0]['destination']
	else:
		logger.error("Destination not found.")
		raise ValueError("Destination not found in appspec.yml")

# Function to install the application
def install(config_section):
	logger.info("Installing")

	# Get the destination from appspec.yml
	destination = get_destination_from_appspec("./" + config_section + "/appspec.yml")
	logger.info(f"Using destination: {destination}")

	execute_shell_script("chmod +x ./" + config_section + "/hooks/*.sh")

	# Execute ApplicationStop.sh
	execute_shell_script("./" + config_section + "/hooks/ApplicationStop.sh")

	# Execute BeforeInstall.sh
	execute_shell_script("./" + config_section + "/hooks/BeforeInstall.sh")

	# Copy contents to the destination
	logger.info(f"Copying contents of ./{config_section}/ to {destination}")
	os.system(f"cp -R ./{config_section}/* {destination}/")

	# Execute AfterInstall.sh
	execute_shell_script("./" + config_section + "/hooks/AfterInstall.sh")

	# Execute ApplicationStart.sh
	execute_shell_script("./" + config_section + "/hooks/ApplicationStart.sh")

def arg_parser():
	parser = argparse.ArgumentParser(description="Deployer Script")
	parser.add_argument("--config-section", help="Configuration section name (default: Settings)", default=None)
	parser.add_argument("--s3-bucket", help="S3 bucket name")
	parser.add_argument("--target-key-file", help="Target file key")
	parser.add_argument("--profile_name", help="Profile name")
	parser.add_argument("--list-configs", action="store_true", help="List all available configuration sections")
	return parser.parse_args()

# Function to check if the LATEST_VERSION file has changed
def has_version_changed(s3_client, bucket_name, file_name, section_name):
	logger.info(f"Checking bucket: {bucket_name}, file: {file_name}")

	last_modified = s3_client.head_object(Bucket=bucket_name, Key=file_name)["LastModified"]
	logger.info(f"Last modified time: {last_modified}")

	if not config.has_option(section_name, "last_fetch_time"):
		last_fetch_time = "1970-01-01 00:00:00+00:00"
	else:
		last_fetch_time = config.get(section_name, "last_fetch_time")

	# Convert the string to a datetime object
	last_fetch_time_obj = datetime.strptime(last_fetch_time, "%Y-%m-%d %H:%M:%S%z")
	logger.info(f"Last fetch time: {last_fetch_time_obj}")

	# Compare the last modified time of the file to the current time.
	if last_fetch_time_obj < last_modified:
		last_fetch_time = last_modified
		logger.info("Updating last_fetch_time")
		config.set(section_name, "last_fetch_time", last_fetch_time.strftime("%Y-%m-%d %H:%M:%S%z"))
		with open(config_file, "w") as f:
			config.write(f)
		return True
	else:
		return False


# Function to download the target file
def download_file(s3_client, s3_bucket, target_file_key, target_file_uri):
	logger.info(f"Downloading file: {target_file_uri}")
	s3_client.download_file(s3_bucket, target_file_key, target_file_key)
	logger.info(f"Download complete: {target_file_key}")


# Function to unzip the downloaded file
def unzip_file(config_section, target_file_key):
	logger.info(f"Unzipping file: {target_file_key} to ./{config_section}/")
	with zipfile.ZipFile(target_file_key, "r") as zip_ref:
		zip_ref.extractall("./" + config_section)
	logger.info("Unzip complete")

def deploy(s3_client, s3_bucket, target_file_key, target_file_uri, config_section):
	logger.info("Version has changed. Downloading new file...")
	download_file(s3_client, s3_bucket, target_file_key, target_file_uri)

	execute_shell_script("rm -rf ./bundle")

	logger.info("Unzipping downloaded file...")
	unzip_file(config_section, target_file_key)

	install(config_section)
	config.set(config_section, "installation_in_progress", "false")
	with open(config_file, "w") as f:
		config.write(f)
  
	cleanup_command = f"rm -rf ./{config_section} && rm -f {target_file_key}"
	logger.info(f"Cleaning up temporary files with command: {cleanup_command}")
	os.system(cleanup_command)
  
def main_for_section(config_section):
	logger.info(f"Using configuration section: {config_section}")

	# Retrieve the values from the configuration file
	if config.has_section(config_section):
		s3_bucket = config.get(config_section, "s3_bucket")
		target_file_key = config.get(config_section, "target_file_key")
		profile_name = config.get(config_section, "profile_name")
	else:
		logger.error(f"Configuration section '{config_section}' not found in config.ini")
		print(f"Error: Configuration section '{config_section}' not found in config.ini")
		print("Available sections:")
		for section in config.sections():
			print(f"  - {section}")
		exit(1)

	# Update the values if provided through command line arguments
	if args.s3_bucket:
		s3_bucket = args.s3_bucket
	if args.target_key_file:
		target_file_key = args.target_key_file
	if args.profile_name:
		profile_name = args.profile_name

	# Update the configuration file if section doesn't exist
	if not config.has_section(config_section):
		config.add_section(config_section)
	config.set(config_section, "s3_bucket", s3_bucket)
	config.set(config_section, "target_file_key", target_file_key)
	config.set(config_section, "profile_name", profile_name)
	with open(config_file, "w") as f:
		config.write(f)

	# Create an AWS session with the specified profile
	session = boto3.Session(profile_name=profile_name)

	# Create an S3 client using the session
	s3_client = session.client("s3")

	# Construct the S3 file URIs
	target_file_uri = f"s3://{s3_bucket}/{target_file_key}"

	installation_in_progress_counter = 0
	interval_seconds = 60
	while True:
		installation_in_progress = config.get(config_section, "installation_in_progress")

		if installation_in_progress_counter > 10:
			logger.error("Installation took more than 10 minutes!")
		elif installation_in_progress == "true":
			logger.error("There is an installation in progress")
			installation_in_progress_counter = installation_in_progress_counter + 1
		else:
			try:
				print("Checking for new version...")
				version_changed = has_version_changed(s3_client=s3_client, bucket_name=s3_bucket, file_name=target_file_key, section_name=config_section)
				if version_changed:
					installation_in_progress_counter = 0
					config.set(config_section, "installation_in_progress", "true")
					with open(config_file, "w") as f:
						config.write(f)
					deploy(s3_client, s3_bucket, target_file_key, target_file_uri, config_section)
				else:
					logger.info("Version not changed")
			except Exception as e:
				logger.error(f"Deployment failed: {e}")
				config.set(config_section, "installation_in_progress", "false")
				with open(config_file, "w") as f:
					config.write(f)
    
		logger.info(f"Sleep for {interval_seconds} seconds before polling again")
		time.sleep(interval_seconds)		

if __name__ == "__main__":
	# Read the configuration file
	config = ConfigParser()
	config_file = "config.ini"
	config.read(config_file)

	# Parse command line arguments
	args = arg_parser()

	if args.list_configs:
		print("Available configuration sections:")
		for section in config.sections():
			print(f"  - {section}")
		exit(0)

	if args.config_section is None:
		threads = []
		for section in config.sections():
			t = threading.Thread(target=main_for_section, args=(section,))
			t.start()
			threads.append(t)
		for t in threads:
			t.join()
	else:
		main_for_section(args.config_section)