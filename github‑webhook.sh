#!/bin/bash

# Log start time
echo "[$(date)] Starting webhook deployment" >> /var/www/u3085459/data/www/sosmark.ru/webhook.log

# Change to the application directory
cd /var/www/u3085459/data/www/sosmark.ru

# Pull latest changes
git pull origin main >> /var/www/u3085459/data/www/sosmark.ru/webhook.log 2>&1

# Install any new dependencies
source /var/www/u3085459/data/flaskenv/bin/activate
pip install -r requirements.txt >> /var/www/u3085459/data/www/sosmark.ru/webhook.log 2>&1

# Restart the application (adjust this based on your setup)
touch /var/www/u3085459/data/www/sosmark.ru/tmp/restart.txt

# Log completion
echo "[$(date)] Deployment completed" >> /var/www/u3085459/data/www/sosmark.ru/webhook.log
