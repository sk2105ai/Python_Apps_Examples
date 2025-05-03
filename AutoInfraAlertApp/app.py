#!/usr/bin/env python3
"""
Directory Size Monitor

This script monitors the size of specified directories and sends email alerts
when the directory size exceeds a defined threshold.

Features:
- Configurable directories to monitor
- Size threshold setting (in bytes, KB, MB, GB)
- Email notifications to multiple recipients
- Logging of operations and errors
- Configuration via separate config file
"""

import os
import sys
import logging
import smtplib
import configparser
import argparse
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('directory_monitor.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

def parse_size(size_str):
    """
    Convert size string with units to bytes
    
    Args:
        size_str (str): Size string (e.g., "100MB", "1.5GB")
    
    Returns:
        int: Size in bytes
        
    Raises:
        ValueError: If the format is invalid
    """
    try:
        # If the string is just a number, return it as bytes
        if size_str.isdigit():
            return int(size_str)
        
        # Extract the numeric part and the unit
        size = float(''.join(c for c in size_str if c.isdigit() or c == '.'))
        unit = ''.join(c for c in size_str if c.isalpha()).upper()
        
        # Convert to bytes based on unit
        if unit == 'KB':
            return int(size * 1024)
        elif unit == 'MB':
            return int(size * 1024 * 1024)
        elif unit == 'GB':
            return int(size * 1024 * 1024 * 1024)
        elif unit == 'TB':
            return int(size * 1024 * 1024 * 1024 * 1024)
        else:
            raise ValueError(f"Unknown size unit: {unit}")
    except Exception as e:
        logger.error(f"Error parsing size string '{size_str}': {str(e)}")
        raise ValueError(f"Invalid size format: {size_str}. Use format like '100MB', '1.5GB', etc.")

def get_directory_size(directory):
    """
    Calculate the total size of a directory recursively
    
    Args:
        directory (str): Path to the directory
    
    Returns:
        int: Size of the directory in bytes
    """
    total_size = 0
    try:
        for dirpath, dirnames, filenames in os.walk(directory):
            for filename in filenames:
                file_path = os.path.join(dirpath, filename)
                # Skip if it's a symbolic link
                if not os.path.islink(file_path):
                    try:
                        total_size += os.path.getsize(file_path)
                    except (OSError, FileNotFoundError) as e:
                        logger.warning(f"Could not get size of {file_path}: {e}")
    except Exception as e:
        logger.error(f"Error calculating directory size for {directory}: {str(e)}")
        raise
    
    return total_size

def format_size(size_bytes):
    """
    Format size in bytes to a human-readable string
    
    Args:
        size_bytes (int): Size in bytes
    
    Returns:
        str: Formatted size string
    """
    # Define units and their thresholds
    units = [('B', 0), ('KB', 1), ('MB', 2), ('GB', 3), ('TB', 4)]
    
    unit_index = 0
    size = float(size_bytes)
    
    # Find appropriate unit
    for unit, index in units:
        if size < 1024 or unit_index == len(units) - 1:
            break
        size /= 1024
        unit_index += 1
    
    # Format with up to 2 decimal places
    if size.is_integer():
        return f"{int(size)} {units[unit_index][0]}"
    else:
        return f"{size:.2f} {units[unit_index][0]}"

def send_email(smtp_config, recipients, subject, message):
    """
    Send email notification
    
    Args:
        smtp_config (dict): SMTP configuration (host, port, username, password, use_tls)
        recipients (list): List of email recipients
        subject (str): Email subject
        message (str): Email message body
    """
    try:
        # Create message
        msg = MIMEMultipart()
        msg['From'] = smtp_config['username']
        msg['To'] = ', '.join(recipients)
        msg['Subject'] = subject
        
        # Attach message body
        msg.attach(MIMEText(message, 'plain'))
        
        # Connect to SMTP server
        with smtplib.SMTP(smtp_config['host'], int(smtp_config['port'])) as server:
            # Use TLS if configured
            if smtp_config.get('use_tls', 'False').lower() == 'true':
                server.starttls()
            
            # Login if credentials provided
            if smtp_config['username'] and smtp_config['password']:
                server.login(smtp_config['username'], smtp_config['password'])
            
            # Send email
            server.send_message(msg)
        
        logger.info(f"Email notification sent to {recipients}")
    except Exception as e:
        logger.error(f"Failed to send email notification: {str(e)}")
        raise

def load_config(config_file):
    """
    Load configuration from file
    
    Args:
        config_file (str): Path to the configuration file
    
    Returns:
        dict: Configuration parameters
    """
    try:
        config = configparser.ConfigParser()
        config.read(config_file)
        
        # Extract directories and thresholds
        directories = {}
        for section in config.sections():
            if section.startswith('directory:'):
                dir_name = section.split(':', 1)[1]
                path = config[section]['path']
                threshold = config[section]['threshold']
                directories[dir_name] = {
                    'path': path,
                    'threshold': threshold
                }
        
        # Extract email configuration
        email_config = {
            'recipients': [email.strip() for email in config['email']['recipients'].split(',')],
            'smtp': {
                'host': config['smtp']['host'],
                'port': config['smtp']['port'],
                'username': config['smtp']['username'],
                'password': config['smtp']['password'],
                'use_tls': config['smtp'].get('use_tls', 'False')
            }
        }
        
        return {
            'directories': directories,
            'email': email_config
        }
    except Exception as e:
        logger.error(f"Error loading configuration from {config_file}: {str(e)}")
        raise

def check_directories(config):
    """
    Check directory sizes against thresholds and send notifications if needed
    
    Args:
        config (dict): Configuration dictionary
    """
    alerts = []
    
    for dir_name, dir_config in config['directories'].items():
        try:
            path = dir_config['path']
            threshold_str = dir_config['threshold']
            
            # Skip if directory doesn't exist
            if not os.path.exists(path):
                logger.warning(f"Directory {path} does not exist. Skipping.")
                continue
            
            # Calculate directory size
            logger.info(f"Checking directory: {path}")
            dir_size = get_directory_size(path)
            threshold_bytes = parse_size(threshold_str)
            
            # Compare with threshold
            if dir_size > threshold_bytes:
                logger.warning(
                    f"Directory {dir_name} ({path}) size {format_size(dir_size)} "
                    f"exceeds threshold {format_size(threshold_bytes)}"
                )
                alerts.append({
                    'name': dir_name,
                    'path': path,
                    'size': dir_size,
                    'threshold': threshold_bytes
                })
        except Exception as e:
            logger.error(f"Error checking directory {dir_name}: {str(e)}")
    
    # Send alerts if any
    if alerts:
        send_alerts(alerts, config['email'])

def send_alerts(alerts, email_config):
    """
    Send email alerts for directories exceeding thresholds
    
    Args:
        alerts (list): List of alert information
        email_config (dict): Email configuration
    """
    try:
        # Format alert message
        hostname = os.uname().nodename if hasattr(os, 'uname') else os.environ.get('COMPUTERNAME', 'unknown')
        subject = f"Directory Size Alert on {hostname} - {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        
        message = "The following directories have exceeded their size thresholds:\n\n"
        for alert in alerts:
            message += f"Directory: {alert['name']} ({alert['path']})\n"
            message += f"Current Size: {format_size(alert['size'])}\n"
            message += f"Threshold: {format_size(alert['threshold'])}\n"
            message += f"Exceeded by: {format_size(alert['size'] - alert['threshold'])}\n\n"
        
        message += f"\nThis is an automated message from the Directory Size Monitor running on {hostname}."
        
        # Send email
        send_email(email_config['smtp'], email_config['recipients'], subject, message)
    except Exception as e:
        logger.error(f"Failed to send alerts: {str(e)}")

def main():
    """
    Main function to run the directory size monitor
    """
    parser = argparse.ArgumentParser(description='Monitor directory sizes and send alerts when thresholds are exceeded')
    parser.add_argument('-c', '--config', default='directory_monitor.ini', help='Path to configuration file')
    args = parser.parse_args()
    
    try:
        logger.info("Starting directory size monitor")
        
        # Load configuration
        logger.info(f"Loading configuration from {args.config}")
        config = load_config(args.config)
        
        # Check directories
        check_directories(config)
        
        logger.info("Directory size check completed successfully")
    except Exception as e:
        logger.error(f"Program error: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    # application entry point
    main()